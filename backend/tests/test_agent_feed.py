"""2026-09-23 regressions: stale bento metrics, LLM plans accepted as `ok`
while useless, and the live agent feed the Advisor chat renders."""
import asyncio
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
import pytest_asyncio
from google.genai import types
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import db
from app.agent import runner
from app.db import get_session
from app.main import app
from app.models.agent import AgentRun, CalendarEventProposal, Recommendation
from app.models.base import Base
from app.models.core import Block, Farm, FlowEdge, User
from app.models.diagnosis import Diagnosis, RiskAssessment
from app.models.knowledge import TreatmentOption
from app.schemas.weather import GetWeatherResult, WeatherForecastOut


@pytest_asyncio.fixture
async def factory(tmp_path):
    # A file DB, so the background task's own session sees the same data.
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _weather(rain_mm: float = 0.0) -> GetWeatherResult:
    today = date.today()
    return GetWeatherResult(
        station_id="t",
        rainfall_7d=[],
        forecast_7d=[
            WeatherForecastOut(station_id="t", forecast_date=(today + timedelta(days=i)).isoformat(),
                               issued_at=today.isoformat(), rainfall_mm=rain_mm, probability=0.5)
            for i in range(7)
        ],
        is_cached_fallback=False,
    )


async def _seed(session):
    """Two blocks: A upslope with collar lesion, B downslope and healthy."""
    user = User(display_name="N", district="Sibu", language_pref="ms")
    session.add(user)
    await session.flush()
    farm = Farm(user_id=user.user_id, name="F", centroid_lat=2.3, centroid_lon=111.8, elevation_tier="minimal")
    session.add(farm)
    await session.flush()
    a = Block(farm_id=farm.farm_id, label="Blok A", photo_uri="x", centroid_lat=2.3, centroid_lon=111.8,
              elevation_rank=1, current_state="harmed")
    b = Block(farm_id=farm.farm_id, label="Blok B", photo_uri="x", centroid_lat=2.3001, centroid_lon=111.8,
              elevation_rank=2)
    session.add_all([a, b])
    await session.flush()
    session.add(FlowEdge(farm_id=farm.farm_id, from_block_id=a.block_id, to_block_id=b.block_id,
                         horizontal_dist_m=12.0, flow_weight=0.8, source="farmer", farmer_confirmed=True))
    diag = Diagnosis(observation_id="o1", predicted_class="collar_lesion", confidence=0.91,
                     all_scores={}, below_threshold=False, model_version="t")
    session.add(diag)
    await session.flush()
    a.last_diagnosis_id = diag.diagnosis_id
    session.add(TreatmentOption(treatment_id="metalaxyl_drench", name_ms="Metalaksil", name_en="Metalaxyl",
                                type="systemic", applies_to=["collar_lesion"], rainfast_hours=24,
                                application_method="drench", source_ref="t"))
    await session.commit()
    return farm, a, b


def _runner_returning(text: str):
    class _R:
        def __init__(self, *a, **k):
            self.session_service = self

        async def create_session(self, **k):
            return None

        async def run_async(self, **k):
            yield SimpleNamespace(
                is_final_response=lambda: True,
                content=types.Content(role="model", parts=[types.Part(text=text)]),
            )

    return _R


@pytest.mark.asyncio
async def test_guard_repairs_a_useless_llm_plan_and_spread_is_real(factory, monkeypatch):
    """The model says no_action for a collar-lesion block, dated 2023, plus a
    rec for a block that doesn't exist. Observed on qwen2.5:14b."""
    async with factory() as session:
        farm, a, b = await _seed(session)
        bad = (
            '{"recommendations": ['
            f'{{"block_id": "{a.block_id}", "action_type": "no_action", "recommended_at": "2023-10-11T14:00:00"}},'
            '{"block_id": "block-123", "action_type": "spray", "recommended_at": "2023-10-11T14:00:00"}]}'
        )
        monkeypatch.setattr(runner, "InMemoryRunner", _runner_returning(bad))
        monkeypatch.setattr(runner, "build_root_agent", lambda *a, **k: object())
        monkeypatch.setattr(runner, "get_weather", lambda farm_id: _weather(0.0))

        run = await runner.run_root_agent(session, farm.farm_id, "diagnose")
        await session.commit()

        recs = (await session.execute(select(Recommendation).where(Recommendation.run_id == run.run_id))).scalars().all()
        assert {r.action_type for r in recs} == {"drench"}, "rules-table treatment replaces the model's no_action"
        assert all(r.recommended_at.year >= 2026 for r in recs)
        guard = next(c for c in run.tools_called if c["name"] == "rules_guard")
        assert guard["args"]["dropped"] == 1 and guard["args"]["added_for"] == [a.block_id]

        # Spread was projected by the deterministic model, not a seed constant.
        risk = (await session.execute(select(RiskAssessment).where(RiskAssessment.run_id == run.run_id))).scalars().all()
        assert [r.block_id for r in risk] == [b.block_id]
        assert risk[0].source_block_id == a.block_id and risk[0].risk_score != 0.85
        # Spec "Block state model" rule 2: projection raises B (never photographed) to alerted.
        # (dry week -> low band -> B stays as it was; see the wet-week test below)
        await session.refresh(b)
        assert b.current_state == ("alerted" if risk[0].risk_band in ("alerted", "harmed") else "protected")

        # A dry forecast -> a schedulable drench -> one proposal awaiting approval.
        props = (await session.execute(select(CalendarEventProposal))).scalars().all()
        assert len(props) == 1 and props[0].status == "pending_approval" and not props[0].approved_by_farmer


@pytest.mark.asyncio
async def test_dashboard_uses_latest_run_and_source_block_spread(factory, monkeypatch):
    async with factory() as session:
        farm, a, b = await _seed(session)
        # Old run: an action scheduled far in the future (used to win the sort).
        old = AgentRun(farm_id=farm.farm_id, trigger="manual", llm_model="t", tools_called=[],
                       started_at=datetime(2026, 9, 1, 8, 0))
        session.add(old)
        await session.flush()
        session.add(Recommendation(run_id=old.run_id, block_id=b.block_id, sequence=1, action_type="inspect",
                                   recommended_at=datetime(2026, 12, 31), reason_ms="old"))
        await session.commit()

        monkeypatch.setattr(runner, "InMemoryRunner", _runner_returning("not json"))
        monkeypatch.setattr(runner, "build_root_agent", lambda *a, **k: object())
        monkeypatch.setattr(runner, "get_weather", lambda farm_id: _weather(0.0))
        await runner.run_root_agent(session, farm.farm_id, "diagnose")
        await session.commit()

        async def _override():
            yield session

        app.dependency_overrides[get_session] = _override
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
                monkeypatch.setattr("app.routers.dashboard.get_weather", lambda farm_id: _weather(0.0))
                body = (await http.get(f"/farms/{farm.farm_id}/dashboard")).json()
        finally:
            app.dependency_overrides.clear()

        assert body["top_action"]["action_type"] == "drench"
        assert body["top_action"]["block_id"] == a.block_id
        # Source block A -> drawer shows the downhill risk A projects onto B.
        assert body["drawer"] is not None and body["drawer"]["risk_score"] != 0.85


@pytest.mark.asyncio
async def test_background_run_streams_agent_events(factory, monkeypatch):
    async with factory() as session:
        farm, a, b = await _seed(session)

    monkeypatch.setattr(runner, "InMemoryRunner", _runner_returning("not json"))
    monkeypatch.setattr(runner, "build_root_agent", lambda *a, **k: object())
    monkeypatch.setattr(runner, "get_weather", lambda farm_id: _weather(0.0))
    monkeypatch.setattr(db, "SessionLocal", factory)

    async def _override():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            started = (await http.post("/agent/run", json={
                "farm_id": farm.farm_id, "message": "diagnose", "background": True,
            })).json()
            assert started["status"] == "running"
            run_id = started["run_id"]

            feed = {}
            for _ in range(100):
                feed = (await http.get(f"/agent/runs/{run_id}/events")).json()
                if feed["done"]:
                    break
                await asyncio.sleep(0.05)
    finally:
        app.dependency_overrides.clear()

    assert feed["status"] == "done"
    agents = [e["agent"] for e in feed["events"]]
    assert agents[0] == "diagnosis_coordinator"
    assert "spread_model" in agents and "calendar_mcp" in agents
    assert any(e["kind"] == "final" for e in feed["events"])
    assert all(e["text_ms"] and e["text_en"] and e["speech_template_id"] for e in feed["events"])

    async with factory() as session:
        row = await session.get(AgentRun, run_id)
        assert row.status == "partial"  # unparseable output -> rules-table fallback, recorded


@pytest.mark.asyncio
async def test_wet_week_projection_raises_downslope_block_to_alerted(factory, monkeypatch):
    """Spec "Block state model" rule 2: L2 alone may raise a never-photographed
    block from protected to alerted. Nothing did this before 2026-09-24."""
    async with factory() as session:
        farm, a, b = await _seed(session)
        monkeypatch.setattr(runner, "InMemoryRunner", _runner_returning("not json"))
        monkeypatch.setattr(runner, "build_root_agent", lambda *a, **k: object())
        monkeypatch.setattr(runner, "get_weather", lambda farm_id: _weather(40.0))
        run = await runner.run_root_agent(session, farm.farm_id, "diagnose")
        await session.commit()

        risk = (await session.execute(select(RiskAssessment).where(RiskAssessment.run_id == run.run_id))).scalars().one()
        assert risk.block_id == b.block_id and risk.risk_band in ("alerted", "harmed")
        await session.refresh(b)
        await session.refresh(a)
        assert b.current_state == "alerted"
        assert a.current_state == "harmed", "projection never touches the diagnosed source block"
