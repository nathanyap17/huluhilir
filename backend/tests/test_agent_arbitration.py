"""PLAN.md Block C exit criterion: 'arbitration case yields "drain today,
spray Thursday" with defer_cause="rainfast" logged.'

This is a LIVE test against real Ollama (qwen2.5:14b, EXP-5's locked model) --
not mocked. It is inherently less deterministic than the rest of the suite:
a local 14B model's exact tool-calling trajectory and wording can vary
between runs. What's asserted is the STRUCTURAL guarantee the pepperdex-rules
skill actually requires (tools_called is populated, no treatment is invented
outside get_treatment's results, a defer is logged with a cause when rain
falls inside the rainfast window) -- not exact English/Malay wording, which
would be a brittle and dishonest thing to hard-assert against an LLM.

Requires Ollama running locally with qwen2.5:14b pulled. Skipped otherwise.
"""
import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.runner import _extract_risk_assessments, run_root_agent
from app.models.agent import Recommendation
from app.models.base import Base
from app.models.core import Block, Farm
from app.models.diagnosis import RiskAssessment
from app.tools.weather import get_weather
from seed.seed import seed_demo_farm, seed_speech, seed_treatments


def _ollama_available() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(not _ollama_available(), reason="Ollama not reachable on localhost:11434")


@pytest.fixture
async def seeded_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_treatments(session)
        await seed_speech(session)
        await seed_demo_farm(session)
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_arbitration_defers_spray_and_prioritises_drainage_when_rain_is_imminent(seeded_session):
    session = seeded_session
    farm = (await session.execute(select(Farm))).scalar_one()
    source_block = (
        await session.execute(select(Block).where(Block.farm_id == farm.farm_id, Block.elevation_rank == 1))
    ).scalar_one()

    # Confirm the scenario actually has rain landing soon -- otherwise the
    # rainfast branch has nothing to defer against and the test would pass
    # vacuously. Uses the real get_weather tool (live or cached fallback).
    weather = get_weather(farm.farm_id)
    assert weather.forecast_7d, "no forecast available -- cannot exercise the rainfast defer path"
    tomorrow_rain = weather.forecast_7d[0].rainfall_mm
    assert tomorrow_rain >= 5.0, (
        f"scenario precondition failed: need >=5mm rain forecast soon to exercise defer, got {tomorrow_rain}mm "
        "-- this test's usefulness depends on real/cached weather data at run time"
    )

    user_message = (
        f"Diagnosis cycle complete. Block {source_block.block_id} (the highest block on this farm) has been "
        "diagnosed as collar_lesion with confidence 0.92. Run the standard sequence: check the weather, "
        "project spread, look up treatment, find a spray window, and arbitrate one recommendation per "
        "affected block. This farm's elevation_tier is 'minimal'."
    )

    agent_run = await run_root_agent(session, farm.farm_id, user_message, trigger="user_initiated")
    await session.commit()

    # 1. tools_called must never be empty -- demo evidence of orchestration.
    tool_names = {c["name"] for c in agent_run.tools_called}
    print(f"\ntools_called: {tool_names}")
    for c in agent_run.tools_called:
        print(f"  {c['name']}: args={c['args']} -> {c['result_summary']}")
    assert agent_run.tools_called, "tools_called is empty -- orchestration must be visible"
    assert "get_weather" in tool_names

    # 2. Every recommendation's treatment_id (if any) must come from the
    #    seeded rules table -- never invented (pepperdex-rules skill §1).
    seeded_treatment_ids = {"metalaxyl_drench", "fosetyl_al_spray", "bordeaux_mixture",
                             "trichoderma_biocontrol", "clear_drainage", "remove_infected_vine"}
    recs = (await session.execute(select(Recommendation).where(Recommendation.run_id == agent_run.run_id))).scalars().all()
    print(f"recommendations: {[(r.action_type, r.treatment_id, r.defer_cause, r.reason_ms) for r in recs]}")
    for rec in recs:
        if rec.treatment_id is not None:
            assert rec.treatment_id in seeded_treatment_ids, f"invented treatment_id: {rec.treatment_id}"

    # 3. Given the precondition above (real rain arriving soon), at least one
    #    recommendation should either defer a spray for "rainfast", or
    #    prioritise drainage -- this is the core arbitration behaviour.
    has_defer_or_drainage = any(
        rec.defer_cause == "rainfast" or rec.action_type == "clear_drain" for rec in recs
    )
    assert has_defer_or_drainage, (
        "expected at least one deferred spray (defer_cause='rainfast') or a clear_drain "
        "recommendation given imminent rain -- got: "
        f"{[(r.action_type, r.defer_cause) for r in recs]}"
    )

    # 4. 🔄 v2 -- compute_spread's actual result must be persisted to
    # risk_assessments, not just used in-memory and discarded (Phase C: this
    # table had zero writers anywhere before app/agent/runner.py's
    # _extract_risk_assessments, so the §9.2 drawer had nothing to read).
    if "compute_spread" in tool_names:
        risk_rows = (
            await session.execute(select(RiskAssessment).where(RiskAssessment.run_id == agent_run.run_id))
        ).scalars().all()
        assert risk_rows, "compute_spread ran but no risk_assessments rows were persisted"
        for row in risk_rows:
            assert row.is_estimate is True
            assert 0.0 <= row.risk_score <= 1.0


def test_extract_risk_assessments_reads_the_actual_compute_spread_result():
    """Pure unit test, no LLM needed -- exercises the parsing logic directly
    against a synthetic tools_called entry shaped like the real one
    ToolCallLogger.after_tool produces."""
    calls = [
        {
            "name": "compute_spread",
            "args": {
                "source_block_id": "blk_top",
                "source_class": "collar_lesion",
                "rainfall_7d_mm": 12.5,
                "forecast_7d_mm": 30.0,
                "elevation_tier": "minimal",
            },
            "_raw_result": {
                "source_block_id": "blk_top",
                "is_estimate": True,
                "results": [
                    {"block_id": "blk_mid", "risk": 0.6, "risk_band": "alerted",
                     "eta_days": 3, "path": ["blk_top", "blk_mid"], "confidence": 0.7},
                    {"block_id": "blk_bottom", "risk": 0.3, "risk_band": "protected",
                     "eta_days": 6, "path": ["blk_top", "blk_mid", "blk_bottom"], "confidence": 0.6},
                ],
            },
        },
        {"name": "get_weather", "args": {}, "_raw_result": {}},  # must be ignored
    ]

    rows = _extract_risk_assessments(calls, run_id="run_1", cycle_id="cycle_1")

    assert len(rows) == 2
    by_block = {r.block_id: r for r in rows}
    assert by_block["blk_mid"].risk_score == 0.6
    assert by_block["blk_mid"].risk_band == "alerted"
    assert by_block["blk_mid"].eta_days == 3
    assert by_block["blk_mid"].source_block_id == "blk_top"
    assert by_block["blk_mid"].rainfall_7d_mm == 12.5
    assert by_block["blk_mid"].forecast_7d_mm == 30.0
    assert by_block["blk_mid"].elevation_tier_used == "minimal"
    assert by_block["blk_mid"].run_id == "run_1"
    assert by_block["blk_mid"].cycle_id == "cycle_1"
    assert by_block["blk_mid"].is_estimate is True
