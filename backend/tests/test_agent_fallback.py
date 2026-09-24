"""When the LLM turn hangs or errors, /agent/run must still write
recommendations -- from the rules table only (2026-09-20: a 600 s litellm
timeout against local Ollama left the Home cards stale)."""
import asyncio
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import runner
from app.config import settings
from app.models.agent import Recommendation
from app.models.base import Base
from app.models.core import Block, Farm, User
from app.models.diagnosis import Diagnosis
from app.models.knowledge import TreatmentOption
from app.schemas.weather import GetWeatherResult, WeatherForecastOut


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


def _weather(rain_mm: float) -> GetWeatherResult:
    today = date.today()
    return GetWeatherResult(
        station_id="t",
        rainfall_7d=[],
        forecast_7d=[
            WeatherForecastOut(
                station_id="t",
                forecast_date=(today + timedelta(days=i)).isoformat(),
                issued_at=today.isoformat(),
                rainfall_mm=rain_mm,
                probability=0.5,
            )
            for i in range(7)
        ],
        is_cached_fallback=False,
    )


async def _seed(session):
    user = User(display_name="N", district="Sibu", language_pref="ms")
    session.add(user)
    await session.flush()
    farm = Farm(user_id=user.user_id, name="F", centroid_lat=2.3, centroid_lon=111.8, elevation_tier="minimal")
    session.add(farm)
    await session.flush()
    block = Block(
        farm_id=farm.farm_id, label="Blok A", photo_uri="x", centroid_lat=2.3, centroid_lon=111.8, elevation_rank=1
    )
    session.add(block)
    await session.flush()
    diag = Diagnosis(
        observation_id="obs1", predicted_class="collar_lesion", confidence=0.9,
        all_scores={}, below_threshold=False, model_version="t",
    )
    session.add(diag)
    await session.flush()
    block.last_diagnosis_id = diag.diagnosis_id
    session.add(
        TreatmentOption(
            treatment_id="phosphonate", name_ms="Fosfonat", name_en="Phosphonate", type="systemic",
            applies_to=["collar_lesion"], rainfast_hours=24, application_method="spray", source_ref="t",
        )
    )
    await session.commit()
    return farm, block


class _HangingRunner:
    def __init__(self, *a, **k):
        self.session_service = self

    async def create_session(self, **k):
        return None

    async def run_async(self, **k):
        await asyncio.sleep(60)
        yield  # pragma: no cover


@pytest.mark.asyncio
@pytest.mark.parametrize("rain_mm, expect_defer", [(0.0, None), (40.0, "rainfast")])
async def test_llm_timeout_falls_back_to_rules_table(session, monkeypatch, rain_mm, expect_defer):
    farm, block = await _seed(session)
    monkeypatch.setattr(runner, "InMemoryRunner", _HangingRunner)
    monkeypatch.setattr(runner, "build_root_agent", lambda *a, **k: object())
    monkeypatch.setattr(runner, "get_weather", lambda farm_id: _weather(rain_mm))
    monkeypatch.setattr(settings, "agent_timeout_s", 0.05)

    run = await runner.run_root_agent(session, farm.farm_id, "diagnose", trigger="manual")
    await session.commit()

    assert run.status == "partial"
    assert any(c["name"] == "deterministic_fallback" for c in run.tools_called)

    recs = (await session.execute(select(Recommendation).order_by(Recommendation.sequence))).scalars().all()
    assert recs, "fallback must still produce recommendations"
    spray = next(r for r in recs if r.action_type == "spray")
    assert spray.treatment_id == "phosphonate"  # from the rules table, never invented
    assert spray.defer_cause == expect_defer
    if expect_defer:
        assert recs[0].action_type == "clear_drain"  # drainage before a deferred spray


@pytest.mark.asyncio
async def test_llm_exception_also_falls_back(session, monkeypatch):
    farm, _ = await _seed(session)

    class _Boom(_HangingRunner):
        async def run_async(self, **k):
            raise RuntimeError("connection refused")
            yield  # pragma: no cover

    monkeypatch.setattr(runner, "InMemoryRunner", _Boom)
    monkeypatch.setattr(runner, "build_root_agent", lambda *a, **k: object())
    monkeypatch.setattr(runner, "get_weather", lambda farm_id: _weather(0.0))

    run = await runner.run_root_agent(session, farm.farm_id, "diagnose")
    assert run.status == "partial"
    fallback = next(c for c in run.tools_called if c["name"] == "deterministic_fallback")
    assert fallback["args"]["reason"].startswith("llm_error")
    # the spread model still runs for the diseased block, so the bento metrics are real
    assert any(c["name"] == "compute_spread" for c in run.tools_called)
