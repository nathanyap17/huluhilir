"""Overrun Council -- docs/PROJECT_SPEC.md §3 L4, rule 12.

EXP-15 (docs/VALIDATION_CHECKLIST.md) already validated the dose-less schema
wall in isolation (sandbox/exp15_council_wall.py, before the real agent was
built). These tests exercise the REAL wiring: farm_state=='overrun' detection
(nothing computed this before Phase C), the deterministic fallback ranking,
and (only when Ollama is reachable) a full live council run producing a real
council_debates row.
"""
import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import CouncilDebate
from app.models.base import Base
from app.models.core import Block, Farm, User
from app.schemas.council import TriageRanking
from app.tools.council import fallback_ranking, get_harmed_blocks, is_farm_overrun


def _ollama_available() -> bool:
    try:
        return httpx.get("http://localhost:11434/api/tags", timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


@pytest_asyncio.fixture
async def session_with_blocks():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = User(display_name="Nathan", district="Julau")
        session.add(user)
        await session.flush()
        farm = Farm(user_id=user.user_id, name="Kebun Ujian", centroid_lat=1.55, centroid_lon=110.35)
        session.add(farm)
        await session.flush()

        blocks = [
            Block(farm_id=farm.farm_id, label="Blok Atas", photo_uri="x", centroid_lat=1.551,
                  centroid_lon=110.351, elevation_rank=1, current_state="harmed", vine_count=40),
            Block(farm_id=farm.farm_id, label="Blok Tengah", photo_uri="x", centroid_lat=1.550,
                  centroid_lon=110.351, elevation_rank=2, current_state="harmed", vine_count=25),
            Block(farm_id=farm.farm_id, label="Blok Bawah", photo_uri="x", centroid_lat=1.549,
                  centroid_lon=110.351, elevation_rank=3, current_state="protected", vine_count=30),
        ]
        session.add_all(blocks)
        await session.commit()
        yield session, farm, blocks
    await engine.dispose()


@pytest.mark.asyncio
async def test_farm_is_overrun_only_with_more_than_one_harmed_block(session_with_blocks):
    session, farm, blocks = session_with_blocks
    overrun, harmed = await is_farm_overrun(session, farm.farm_id)
    assert overrun is True
    assert {b.block_id for b in harmed} == {blocks[0].block_id, blocks[1].block_id}


@pytest.mark.asyncio
async def test_farm_not_overrun_with_zero_or_one_harmed_block(session_with_blocks):
    session, farm, blocks = session_with_blocks
    # Demote one of the two harmed blocks -- only one harmed left.
    blocks[1].current_state = "alerted"
    await session.commit()

    overrun, harmed = await is_farm_overrun(session, farm.farm_id)
    assert overrun is False
    assert len(harmed) == 1


@pytest.mark.asyncio
async def test_get_harmed_blocks_excludes_other_states(session_with_blocks):
    session, farm, blocks = session_with_blocks
    harmed = await get_harmed_blocks(session, farm.farm_id)
    assert all(b.current_state == "harmed" for b in harmed)


def test_fallback_ranking_orders_by_elevation_rank_and_is_dose_less():
    blocks = [
        Block(block_id="b3", farm_id="f", label="C", photo_uri="x", centroid_lat=0, centroid_lon=0, elevation_rank=3),
        Block(block_id="b1", farm_id="f", label="A", photo_uri="x", centroid_lat=0, centroid_lon=0, elevation_rank=1),
    ]
    ranking = fallback_ranking(blocks)

    assert ranking[0]["block_id"] == "b1"  # rank 1 = highest = elevation_rank 1
    assert ranking[0]["rank"] == 1
    assert ranking[1]["block_id"] == "b3"
    assert ranking[1]["rank"] == 2

    # Every item must actually satisfy the dose-less wall itself.
    for item in ranking:
        TriageRanking(**item)  # raises ValidationError if this ever regresses


def test_triage_ranking_rejects_a_smuggled_treatment():
    with pytest.raises(ValidationError):
        TriageRanking(block_id="b1", rank=1, rationale_ms="test", treatment_id="sneaky")


pytestmark_live = pytest.mark.skipif(not _ollama_available(), reason="Ollama not reachable on localhost:11434")


@pytestmark_live
@pytest.mark.asyncio
async def test_live_council_run_produces_a_valid_ranking_and_debate_row(session_with_blocks):
    from app.agent.council_agent import run_overrun_council

    session, farm, blocks = session_with_blocks
    harmed = [b for b in blocks if b.current_state == "harmed"]

    ranking = await run_overrun_council(session, farm.farm_id, run_id="run_test_1", harmed_blocks=harmed)
    await session.commit()

    assert {r["block_id"] for r in ranking} == {b.block_id for b in harmed}
    ranks = sorted(r["rank"] for r in ranking)
    assert ranks == list(range(1, len(harmed) + 1))
    for item in ranking:
        TriageRanking(**item)  # the wall must hold on the REAL LLM output too

    debate = (
        await session.execute(select(CouncilDebate).where(CouncilDebate.run_id == "run_test_1"))
    ).scalar_one()
    assert set(debate.block_ids_considered) == {b.block_id for b in harmed}
    assert len(debate.transcript) == 3
    assert all(entry["argument"] for entry in debate.transcript), (
        "a specialist's argument was empty -- state wasn't captured from the nested council session"
    )
