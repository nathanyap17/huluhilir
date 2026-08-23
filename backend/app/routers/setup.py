"""Setup flow endpoints. docs/PROJECT_SPEC.md §5.

Covers registration -> farm -> walk session -> block capture -> elevation
resolution. The Flutter app (Block D) drives these in order; the
SetupCoordinator agent only ever *prompts*, it never writes these rows.

huluhilir-rules skill §4: no land boundary, polygon, or ownership field is
accepted or stored anywhere here -- only point centroids and elevation_rank
ordering.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.base import now_kuching
from app.models.core import Block, ElevationConflict, Farm, FlowEdge, User, WalkSample, WalkSession
from app.schemas.farm import (
    BlockOut,
    FarmCreate,
    FarmOut,
    UserCreate,
    UserOut,
    WalkSampleCreate,
    WalkSessionOut,
)
from app.tools.graph import build_flow_edges, median_centroid, pairs_needing_farmer_input, resolve_elevation_ranks

router = APIRouter(tags=["setup"])


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(req: UserCreate, session: AsyncSession = Depends(get_session)) -> UserOut:
    user = User(**req.model_dump())
    session.add(user)
    await session.commit()
    return UserOut.model_validate(user)


@router.post("/farms", response_model=FarmOut, status_code=201)
async def create_farm(req: FarmCreate, session: AsyncSession = Depends(get_session)) -> FarmOut:
    """elevation_tier is derived from the device probe, never asked -- detection
    is automatic and silent (docs/PROJECT_SPEC.md §4)."""
    farm = Farm(
        **req.model_dump(),
        elevation_tier="optimised" if req.barometer_available else "minimal",
    )
    session.add(farm)
    await session.commit()
    return FarmOut.model_validate(farm)


@router.post("/farms/{farm_id}/walk-sessions", response_model=WalkSessionOut, status_code=201)
async def start_walk_session(
    farm_id: str,
    baseline_pressure_hpa: Optional[float] = None,
    session: AsyncSession = Depends(get_session),
) -> WalkSessionOut:
    """baseline_pressure_hpa is the reference for every relative altitude in
    this session (docs/DATA_MODEL.md §3) -- null on MINIMAL-tier devices."""
    walk = WalkSession(
        farm_id=farm_id,
        baseline_pressure_hpa=baseline_pressure_hpa,
        baseline_captured_at=now_kuching() if baseline_pressure_hpa is not None else None,
    )
    session.add(walk)
    await session.flush()

    farm = await session.get(Farm, farm_id)
    if farm is not None:
        farm.walk_session_id = walk.walk_session_id
    await session.commit()
    return WalkSessionOut.model_validate(walk)


class WalkSampleBatch(BaseModel):
    """The phone buffers samples offline and flushes them in batches -- one
    HTTP call per sample would be unusable on venue/rural connectivity."""
    samples: list[WalkSampleCreate]


@router.post("/walk-sessions/{walk_session_id}/samples", status_code=201)
async def append_walk_samples(
    walk_session_id: str, batch: WalkSampleBatch, session: AsyncSession = Depends(get_session)
) -> dict:
    walk = await session.get(WalkSession, walk_session_id)
    if walk is None:
        raise HTTPException(404, "walk session not found")

    for sample in batch.samples:
        session.add(WalkSample(**sample.model_dump()))

    walk.total_samples += len(batch.samples)
    accuracies = [s.gps_accuracy_m for s in batch.samples]
    if accuracies:
        # Running mean across batches, weighted by count so far.
        prior_n = walk.total_samples - len(batch.samples)
        prior_mean = walk.mean_gps_accuracy_m or 0.0
        walk.mean_gps_accuracy_m = (prior_mean * prior_n + sum(accuracies)) / walk.total_samples

    await session.commit()
    return {"accepted": len(batch.samples), "total_samples": walk.total_samples}


class BlockCaptureRequest(BaseModel):
    label: str = Field(max_length=30, description="Farmer's own words")
    photo_uri: str
    voice_label_uri: Optional[str] = Field(
        default=None, description="Audio blob URI -- stored and replayed, NEVER transcribed"
    )
    position_samples: list[tuple[float, float]] = Field(
        description="(lat, lon) pairs from the +/-5s capture window; centroid is their median"
    )
    baro_rel_m: Optional[float] = None
    drainage: str = "fair"
    area_ha: Optional[float] = None
    vine_count: Optional[int] = None
    variety: Optional[str] = None
    is_external: bool = False
    external_owner_name: Optional[str] = None
    external_owner_phone: Optional[str] = None


@router.post("/farms/{farm_id}/blocks", response_model=BlockOut, status_code=201)
async def capture_block(
    farm_id: str, req: BlockCaptureRequest, session: AsyncSession = Depends(get_session)
) -> BlockOut:
    """elevation_rank is assigned provisionally in capture order here and
    OVERWRITTEN by /resolve-elevation once every block exists -- true ranking
    is only possible after the walk completes (docs/PROJECT_SPEC.md §5 ⑤)."""
    lat, lon = median_centroid(req.position_samples)

    existing = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    provisional_rank = len(existing) + 1

    payload = req.model_dump(exclude={"position_samples"})
    block = Block(
        farm_id=farm_id,
        centroid_lat=lat,
        centroid_lon=lon,
        elevation_rank=provisional_rank,
        **payload,
    )
    session.add(block)
    await session.commit()
    return BlockOut.model_validate(block)


@router.get("/farms/{farm_id}/elevation-questions")
async def get_elevation_questions(farm_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Which block pairs must the farmer be asked to compare?

    MINIMAL: every adjacent pair (n-1 questions).
    OPTIMISED: only pairs the barometer cannot separate (Δh < 2.0 m).
    """
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")

    blocks = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    baro = {b.block_id: b.baro_rel_m for b in blocks if b.baro_rel_m is not None} or None
    if farm.elevation_tier == "minimal":
        baro = None

    pairs = pairs_needing_farmer_input([b.block_id for b in blocks], baro)
    labels = {b.block_id: b.label for b in blocks}
    return {
        "elevation_tier": farm.elevation_tier,
        "questions": [
            {"block_a_id": a, "block_b_id": b, "block_a_label": labels.get(a), "block_b_label": labels.get(b)}
            for a, b in pairs
        ],
    }


class ElevationAnswer(BaseModel):
    block_a_id: str
    block_b_id: str
    answer: str = Field(description="'a_higher' or 'b_higher' -- the farmer's answer, always authoritative")


class ResolveElevationRequest(BaseModel):
    answers: list[ElevationAnswer]


@router.post("/farms/{farm_id}/resolve-elevation")
async def resolve_elevation(
    farm_id: str, req: ResolveElevationRequest, session: AsyncSession = Depends(get_session)
) -> dict:
    """Assign final elevation_ranks and rebuild the flow-edge graph.

    The farmer's answers always win; any barometer disagreement is written to
    elevation_conflicts with resolution='farmer' (huluhilir-rules skill §3).
    """
    blocks = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    if not blocks:
        raise HTTPException(400, "farm has no blocks to rank")

    baro = {b.block_id: b.baro_rel_m for b in blocks if b.baro_rel_m is not None} or None
    farmer_pairs = {(a.block_a_id, a.block_b_id): a.answer for a in req.answers}

    ranks, conflicts = resolve_elevation_ranks([b.block_id for b in blocks], farmer_pairs, baro)

    for block in blocks:
        block.elevation_rank = ranks[block.block_id]

    for conflict in conflicts:
        session.add(ElevationConflict(farm_id=farm_id, **conflict))

    # Rebuild edges from scratch -- ranks changed, so the old set is invalid.
    for old_edge in (await session.execute(select(FlowEdge).where(FlowEdge.farm_id == farm_id))).scalars().all():
        await session.delete(old_edge)
    await session.flush()

    blocks.sort(key=lambda b: b.elevation_rank)
    edges = build_flow_edges(farm_id, blocks)
    for edge in edges:
        session.add(edge)

    farm = await session.get(Farm, farm_id)
    if farm is not None:
        farm.setup_completed_at = now_kuching()

    await session.commit()
    return {
        "ranks": ranks,
        "edges_created": len(edges),
        "conflicts_logged": len(conflicts),
        "setup_completed": True,
    }
