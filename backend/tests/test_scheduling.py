"""v14 fixes (2026-09-24): compute_spread no longer asks the model for data
the server holds; calendar proposals land in real field-work slots; the
Priority card's "Add to calendar" gets its proposal card on demand."""
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent import tools as agent_tools
from app.db import get_session
from app.main import app
from app.models.agent import AgentRun, Recommendation
from app.models.base import Base
from app.models.core import Block, Farm, FlowEdge, User
from app.models.diagnosis import Diagnosis
from app.schemas.weather import GetWeatherResult, WeatherForecastOut
from app.tools.scheduling import workable_slot

NOW = datetime(2026, 9, 24, 15, 0)  # a Thursday, 3 pm


@pytest.mark.parametrize("when, expected", [
    (NOW, datetime(2026, 9, 24, 16, 0)),                      # "now" -> next hour, not 3-4 pm
    (datetime(2026, 9, 24, 15, 10), datetime(2026, 9, 24, 16, 0)),
    (datetime(2026, 9, 26, 0, 0), datetime(2026, 9, 26, 8, 0)),   # date-only window -> morning
    (datetime(2026, 9, 24, 17, 45), datetime(2026, 9, 25, 8, 0)),  # after field hours -> next morning
    (datetime(2026, 9, 25, 5, 30), datetime(2026, 9, 25, 8, 0)),   # before field hours -> 8 am
    (datetime(2026, 9, 25, 10, 0), datetime(2026, 9, 25, 10, 0)),  # a sane future slot is kept
])
def test_workable_slot(when, expected):
    assert workable_slot(when, NOW) == expected


def test_slot_near_end_of_day_rolls_to_tomorrow():
    assert workable_slot(datetime(2026, 9, 24, 17, 0), datetime(2026, 9, 24, 16, 50)) == datetime(2026, 9, 25, 8, 0)


@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        user = User(display_name="N", district="Sibu", language_pref="ms")
        s.add(user)
        await s.flush()
        farm = Farm(user_id=user.user_id, name="F", centroid_lat=2.3, centroid_lon=111.8, elevation_tier="minimal")
        s.add(farm)
        await s.flush()
        a = Block(farm_id=farm.farm_id, label="A", photo_uri="x", centroid_lat=2.3, centroid_lon=111.8, elevation_rank=1)
        b = Block(farm_id=farm.farm_id, label="B", photo_uri="x", centroid_lat=2.3001, centroid_lon=111.8, elevation_rank=2)
        s.add_all([a, b])
        await s.flush()
        s.add(FlowEdge(farm_id=farm.farm_id, from_block_id=a.block_id, to_block_id=b.block_id,
                       horizontal_dist_m=12.0, flow_weight=0.8, source="farmer", farmer_confirmed=True))
        d = Diagnosis(observation_id="o", predicted_class="collar_lesion", confidence=0.9,
                      all_scores={}, below_threshold=False, model_version="t")
        s.add(d)
        await s.flush()
        a.last_diagnosis_id = d.diagnosis_id
        await s.commit()
        yield s, farm, a, b
    await engine.dispose()


def _weather(mm):
    today = date.today()
    return GetWeatherResult(station_id="t", rainfall_7d=[], is_cached_fallback=False, forecast_7d=[
        WeatherForecastOut(station_id="t", forecast_date=(today + timedelta(days=i)).isoformat(),
                           issued_at=today.isoformat(), rainfall_mm=mm, probability=0.5) for i in range(7)])


@pytest.mark.asyncio
async def test_compute_spread_tool_needs_only_a_block_id(seeded, monkeypatch):
    session, farm, a, b = seeded
    monkeypatch.setattr(agent_tools, "get_weather_impl", lambda farm_id: _weather(30.0))
    tool = next(t for t in agent_tools.build_tools(session, farm.farm_id) if t.name == "compute_spread")

    res = await tool.func(source_block_id=a.block_id)
    res = res.model_dump() if hasattr(res, "model_dump") else res
    assert res["source_block_id"] == a.block_id and [r["block_id"] for r in res["results"]] == [b.block_id]

    # A made-up id or an undiagnosed block is a clear error, not a crash.
    assert "error" in (await tool.func(source_block_id="block-123"))
    assert "error" in (await tool.func(source_block_id=b.block_id))


@pytest.mark.asyncio
async def test_add_to_calendar_returns_one_pending_proposal(seeded):
    session, farm, a, _ = seeded
    run = AgentRun(farm_id=farm.farm_id, trigger="manual", llm_model="t", tools_called=[])
    session.add(run)
    await session.flush()
    rec = Recommendation(run_id=run.run_id, block_id=a.block_id, sequence=1, action_type="drench",
                         recommended_at=datetime(2030, 1, 3), reason_ms="r")
    skip = Recommendation(run_id=run.run_id, block_id=a.block_id, sequence=2, action_type="inspect",
                          recommended_at=datetime(2030, 1, 3), reason_ms="r")
    session.add_all([rec, skip])
    await session.commit()

    async def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            first = (await http.post(f"/recommendations/{rec.recommendation_id}/calendar-proposal")).json()
            again = (await http.post(f"/recommendations/{rec.recommendation_id}/calendar-proposal")).json()
            bad = await http.post(f"/recommendations/{skip.recommendation_id}/calendar-proposal")
    finally:
        app.dependency_overrides.clear()

    assert first["status"] == "pending_approval" and not first["approved_by_farmer"]
    assert first["proposal_id"] == again["proposal_id"], "no duplicate cards on repeated taps"
    assert first["start_time"].startswith("2030-01-03T08:00"), "date-only window -> 8 am"
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_find_spray_window_tool_uses_rules_table_and_real_forecast(seeded, monkeypatch):
    """The model used to pass its own forecast (observed: dates in 2023) and
    rainfast hours; now it passes only the treatment id."""
    from app.models.knowledge import TreatmentOption

    session, farm, a, _ = seeded
    session.add(TreatmentOption(treatment_id="bordeaux", name_ms="B", name_en="B", type="contact",
                                applies_to=["collar_lesion"], rainfast_hours=24, application_method="spray",
                                source_ref="t"))
    await session.commit()
    monkeypatch.setattr(agent_tools, "get_weather_impl", lambda farm_id: _weather(40.0))
    tool = next(t for t in agent_tools.build_tools(session, farm.farm_id) if t.name == "find_spray_window")

    res = await tool.func(treatment_id="bordeaux")
    res = res.model_dump() if hasattr(res, "model_dump") else res
    assert res["rainfast_hours"] == 24, "rain-fast hours come from the rules table"
    assert res["defer_cause"] == "rainfast", "a wet week (real forecast) defers the spray"
    assert all(str(w["window_start"]).startswith(str(date.today().year)) for w in res["viable_windows"])
    assert "error" in (await tool.func(treatment_id="made_up"))


def test_consecutive_steps_from_one_agent_become_one_message():
    """Two diseased blocks -> two get_treatment calls -> the feed showed the
    Rules Table twice. Now the second replaces the first with combined text."""
    from app.agent import progress

    progress.start("r1")
    progress.emit("r1", "spread_model", "a", "rain")
    progress.emit("r1", "rules_table", "b1", "treatments for block 1")
    progress.emit("r1", "rules_table", "b2", "treatments for block 2")
    progress.emit("r1", "rules_table", "b2", "treatments for block 2")  # exact repeat: ignored
    progress.emit("r1", "root_agent", "w", "warning", kind="warning")
    progress.emit("r1", "root_agent", "w2", "warning 2", kind="warning")  # warnings stay separate

    events = progress.get("r1").events
    assert [e["agent"] for e in events] == ["spread_model", "rules_table", "root_agent", "root_agent"]
    merged = events[1]
    assert merged["text_en"] == "treatments for block 1\ntreatments for block 2"
    assert merged["replaces"] == 1 and merged["seq"] == 2
    assert [e["seq"] for e in events] == sorted({e["seq"] for e in events}), "seq stays unique and ordered"
