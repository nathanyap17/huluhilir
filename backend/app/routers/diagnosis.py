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
    # force_accept is a request-level decision, not a stored column -- it is
    # excluded rather than added to the table, because what matters
    # afterwards is the diagnosis and its confidence, not which button the
    # farmer pressed to get past a retake prompt.
    observation = Observation(**req.model_dump(exclude={"force_accept"}))
    session.add(observation)
    await session.flush()

    # image_uri arrives as the "/media/<hash>.jpg" URI the upload returned;
    # resolve it back to a real path for the ONNX runtime.
    filename = Path(req.image_uri).name
    local_path = Path(settings.media_root) / filename
    if not local_path.is_file():
        raise HTTPException(400, f"image not found on server: {req.image_uri}")

    # Backend is configuration, not a code branch anyone downstream sees:
    # both paths return the same six-class DiagnoseLeafResult, and neither can
    # reach the rules table (huluhilir-rules §2).
    if settings.classifier_backend == "gemini":
        from app.tools.diagnose_gemini import diagnose_leaf_gemini

        try:
            result = await diagnose_leaf_gemini(
                observation.observation_id, str(local_path), CaptureTarget(req.capture_target)
            )
        except Exception as exc:
            # A vision call needs the network and can fail; the trained model
            # is local and always available, so it is the fallback rather than
            # the request erroring out on a farmer mid-cycle.
            #
            # The reason is printed rather than logged: uvicorn's logging
            # config on Cloud Run does not propagate module loggers to stdout,
            # which made an earlier failure invisible and cost hours of
            # guessing. print() reaches Cloud Logging reliably.
            print(
                f"[classifier] gemini backend failed, falling back to CNN: "
                f"{type(exc).__name__}: {str(exc)[:400]}",
                flush=True,
            )
            result = diagnose_leaf(
                observation.observation_id, str(local_path), CaptureTarget(req.capture_target)
            )
    else:
        result = diagnose_leaf(
            observation.observation_id, str(local_path), CaptureTarget(req.capture_target)
        )

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

    # How many photos has this block already had in this cycle? A retake
    # prompt is useful the first time and a trap by the third: the previous
    # rule was "a mismatched photo never counts", which meant a block the
    # model kept calling `unrelated` could NEVER be completed and the whole
    # cycle stalled on it with no way forward. Confirmed in the field.
    prior_attempts = 0
    if req.cycle_id:
        prior_attempts = len((
            await session.execute(
                select(Observation).where(
                    Observation.cycle_id == req.cycle_id,
                    Observation.block_id == req.block_id,
                    Observation.observation_id != observation.observation_id,
                )
            )
        ).scalars().all())

    # The farmer can always override. They are standing in front of the vine
    # and the model is not (huluhilir-rules section 3 is the same principle).
    forced = bool(req.force_accept)

    # After MAX_RETAKES rejected attempts the photo is accepted anyway, with
    # the diagnosis flagged low-confidence rather than discarded. A farmer who
    # has photographed the same stem three times has told us something the
    # classifier has not.
    MAX_RETAKES = 2
    exhausted = prior_attempts >= MAX_RETAKES

    counts_as_check = result.mismatch_flag is None or forced or exhausted

    # Captured BEFORE the update below, because it is the evidence of whether
    # this block has already been counted in this cycle.
    prior_last_diagnosis_id = block.last_diagnosis_id if block is not None else None

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
            # Progress advances once per block, on its first ACCEPTED photo.
            #
            # Counting observation rows cannot express that: every attempt is
            # stored, accepted or not, so "rows <= 1" wrongly suppressed the
            # increment for a block whose first try was rejected, and the
            # clause added to compensate (`or prior_attempts >= 1`) reduced to
            # `prior_attempts == 0 or prior_attempts >= 1` -- always true, so
            # every photo incremented and a single block could complete the
            # whole cycle on its own.
            #
            # `block.last_diagnosis_id` is the honest signal: it is only ever
            # set on an accepted photo. If it already pointed at a diagnosis
            # from THIS cycle, this block is counted; otherwise it is not.
            # No schema change, and idempotent under repeat captures.
            already_counted = False
            if prior_last_diagnosis_id:
                prior = await session.get(Diagnosis, prior_last_diagnosis_id)
                already_counted = prior is not None and prior.cycle_id == req.cycle_id

            if not already_counted:
                cycle.blocks_captured += 1
            if cycle.blocks_captured >= cycle.blocks_total:
                cycle.status = "complete"
                cycle.completed_at = now_kuching()

    await session.commit()

    # The authoritative cycle state, returned with the observation that
    # changed it. Without this the client had to re-GET
    # /diagnosis-cycles/current, which filters on status == "in_progress" and
    # therefore returns NULL the instant a cycle completes -- so the app kept
    # its stale copy and froze one short of the total. Reading the counter
    # from the response that produced it removes both the round trip and the
    # inference.
    cycle_state = None
    if req.cycle_id:
        c = await session.get(DiagnosisCycle, req.cycle_id)
        if c is not None:
            cycle_state = {
                "cycle_id": c.cycle_id,
                "blocks_total": c.blocks_total,
                "blocks_captured": c.blocks_captured,
                "status": c.status,
            }

    return {
        "observation_id": observation.observation_id,
        "cycle": cycle_state,
        "diagnosis": result.model_dump(mode="json"),
        "counts_as_check": counts_as_check,
        "retake_prompt": result.mismatch_flag,
        # Lets the app offer a way forward instead of looping: how many tries
        # this block has had, and whether the next rejection will be accepted
        # anyway. Without these the UI cannot tell "try again" from "stuck".
        "attempt": prior_attempts + 1,
        "retakes_remaining": max(0, MAX_RETAKES - prior_attempts),
        "accepted_despite_mismatch": counts_as_check and result.mismatch_flag is not None,
    }
