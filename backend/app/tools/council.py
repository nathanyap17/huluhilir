"""Overrun detection + deterministic fallback ranking. docs/PROJECT_SPEC.md §3 L4.

`farm_state == 'overrun'` has no stored column anywhere (it's `BlockState.
overrun` in the enum, but no block or farm row is ever actually set to it --
verified by grep before writing this: nothing in the pre-Phase-C codebase
computed it). It is DERIVED, farm-wide: more than one block simultaneously
`harmed`. Computed here rather than trusted to the LLM, matching this
project's established pattern (loop/termination checks are deterministic
Python, never LLM judgement -- google-adk skill).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Block


async def get_harmed_blocks(session: AsyncSession, farm_id: str) -> list[Block]:
    result = await session.execute(
        select(Block).where(Block.farm_id == farm_id, Block.current_state == "harmed")
    )
    return list(result.scalars().all())


async def is_farm_overrun(session: AsyncSession, farm_id: str) -> tuple[bool, list[Block]]:
    """Returns (is_overrun, harmed_blocks). is_overrun is True only when MORE
    THAN ONE block is simultaneously harmed -- a single harmed block is
    ordinary triage with a single deterministic priority, not an overrun
    (docs/PROJECT_SPEC.md §3 L4: 'fires only during Overrun-state triage:
    multiple simultaneously-Harmed blocks with no single deterministic
    priority order')."""
    harmed = await get_harmed_blocks(session, farm_id)
    return len(harmed) > 1, harmed


def fallback_ranking(harmed_blocks: list[Block]) -> list[dict]:
    """PLAN.md §5 cut order: 'Overrun Council -> deterministic triage (sort
    by risk score) instead of a real debate.' Used both as the documented
    degraded mode AND as the safety net when the council's own LLM output
    fails to parse or fails the dose-less schema wall -- either way, the
    farmer still gets a ranking, never an error.

    Sorts by elevation_rank (lower = higher = more urgent for downhill
    spread) since that is always available; a real risk_score requires a
    compute_spread run to already exist for these blocks, which is not
    guaranteed at triage time.
    """
    ordered = sorted(harmed_blocks, key=lambda b: b.elevation_rank)
    return [
        {
            "block_id": b.block_id,
            "rank": i + 1,
            "rationale_ms": f"Diutamakan mengikut kedudukan tinggi (kedudukan #{b.elevation_rank}).",
        }
        for i, b in enumerate(ordered)
    ]
