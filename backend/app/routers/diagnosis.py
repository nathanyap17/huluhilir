"""Diagnosis cycle endpoints. docs/PROJECT_SPEC.md §6.

A diagnosis is an EVENT covering all blocks, not a per-photo action, and it
is resumable across app restarts -- `status='in_progress'` survives so the UI
can offer "Sambung diagnosis (4/6 blok)".
"""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models.base import now_kuching
from app.models.core import Block
from app.models.diagnosis import Diagnosis, DiagnosisCycle, Observation
from app.schemas.diagnosis import DiagnosisCycleOut, ObservationCreate
from app.schemas.enums import CaptureTarget
from app.tools.diagnose import diagnose_leaf

router = APIRouter(tags=["diagnosis"])

# Presence, not prevalence: any photo in a cycle returning one of these sets
# the whole block's state, however many other photos came back healthy
# (docs/PROJECT_SPEC.md §6 "worst-class-wins").
_HARMED_CLASSES = {"collar_lesion", "defoliation_wilt"}
_ALERTED_CLASSES = {"foliar_yellowing"}


class StartCycleRequest(BaseModel):
    trigger_reason: str = "user_initiated"
    triggering_rain_mm: Optional[float] = None
    triggering_rain_date: Optional[str] = None


@router.post("/farms/{farm_id}/diagnosis-cycles", response_model=DiagnosisCycleOut, status_code=201)
async def start_cycle(
    farm_id: str, req: StartCycleRequest, session: AsyncSession = Depends(get_session)
) -> DiagnosisCycleOut:
    """Resumes an existing in-progress cycle rather than starting a second
    one -- two open cycles for one farm would make blocks_captured meaningless."""
    existing = (
        await session.execute(
            select(DiagnosisCycle).where(
                DiagnosisCycle.farm_id == farm_id, DiagnosisCycle.status == "in_progress"
            )
        )
    ).scalars().first()
    if existing is not None:
        return DiagnosisCycleOut.model_validate(existing)

    blocks = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    own_blocks = [b for b in blocks if not b.is_external]
    if not own_blocks:
        raise HTTPException(400, "farm has no blocks to diagnose")

    cycle = DiagnosisCycle(
        farm_id=farm_id,
        trigger_reason=req.trigger_reason,
        triggering_rain_mm=req.triggering_rain_mm,
        triggering_rain_date=req.triggering_rain_date,
        blocks_total=len(own_blocks),
    )
    session.add(cycle)
    await session.commit()
    return DiagnosisCycleOut.model_validate(cycle)


@router.get("/farms/{farm_id}/diagnosis-cycles/current", response_model=Optional[DiagnosisCycleOut])
async def get_current_cycle(farm_id: str, session: AsyncSession = Depends(get_session)):
    """Drives the "Sambung diagnosis (4/6 blok)" resume prompt. Returns null
    when there is nothing to resume."""
    cycle = (
        await session.execute(
            select(DiagnosisCycle).where(
                DiagnosisCycle.farm_id == farm_id, DiagnosisCycle.status == "in_progress"
            )
        )
    ).scalars().first()
    return DiagnosisCycleOut.model_validate(cycle) if cycle else None


@router.post("/observations")
async def create_observation(req: ObservationCreate, session: AsyncSession = Depends(get_session)) -> dict:
    """Record a photo and classify it immediately.

    Returns the diagnosis alongside a `mismatch_flag` when the model's
    predicted body part contradicts `capture_target` -- the UI must prompt a
    RETAKE in that case and NOT treat it as a completed check
    (huluhilir-rules skill §9). A mismatched or `unrelated` photo deliberately
    does not advance `blocks_captured`.
    """
    observation = Observation(**req.model_dump())
    session.add(observation)
    await session.flush()

    # image_uri arrives as the "/media/<hash>.jpg" URI the upload returned;
    # resolve it back to a real path for the ONNX runtime.
    filename = Path(req.image_uri).name
    local_path = Path(settings.media_root) / filename
    if not local_path.is_file():
        raise HTTPException(400, f"image not found on server: {req.image_uri}")

    result = diagnose_leaf(observation.observation_id, str(local_path), CaptureTarget(req.capture_target))

    diagnosis = Diagnosis(
        observation_id=observation.observation_id,
        cycle_id=req.cycle_id,
        predicted_class=result.predicted_class,
        confidence=result.confidence,
        all_scores=result.all_scores,
        second_class=result.second_class,
        below_threshold=result.below_threshold,
        model_version=result.model_version,
        inference_ms=result.inference_ms,
    )
    session.add(diagnosis)
    await session.flush()

    block = await session.get(Block, req.block_id)
    counts_as_check = result.mismatch_flag is None

    if block is not None and counts_as_check:
        block.last_diagnosis_id = diagnosis.diagnosis_id
        # Worst-class-wins: never downgrade a block within a cycle.
        if result.predicted_class in _HARMED_CLASSES:
            block.current_state = "harmed"
            block.state_changed_at = now_kuching()
        elif result.predicted_class in _ALERTED_CLASSES and block.current_state == "protected":
            block.current_state = "alerted"
            block.state_changed_at = now_kuching()

    if req.cycle_id and counts_as_check:
        cycle = await session.get(DiagnosisCycle, req.cycle_id)
        if cycle is not None:
            already = (
                await session.execute(
                    select(Observation).where(
                        Observation.cycle_id == req.cycle_id, Observation.block_id == req.block_id
                    )
                )
            ).scalars().all()
            # Only the FIRST accepted photo per block advances progress --
            # multi-sample capture (2-4 photos/block) must not overcount.
            if len(already) <= 1:
                cycle.blocks_captured += 1
            if cycle.blocks_captured >= cycle.blocks_total:
                cycle.status = "complete"
                cycle.completed_at = now_kuching()

    await session.commit()
    return {
        "observation_id": observation.observation_id,
        "diagnosis": result.model_dump(mode="json"),
        "counts_as_check": counts_as_check,
        "retake_prompt": result.mismatch_flag,
    }
