"""Setup flow endpoints. docs/PROJECT_SPEC.md §5.

Covers registration -> farm -> walk session -> block capture -> elevation
resolution. The Flutter app (Block D) drives these in order; the
SetupCoordinator agent only ever *prompts*, it never writes these rows.

pepperdex-rules skill §4: no land boundary, polygon, or ownership field is
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
from app.models.core import (
    Block, ElevationConflict, Farm, FarmRestoreCode, FlowEdge, User, WalkSample, WalkSession,
)
from app.schemas.farm import (
    BlockOut,
    FarmCreate,
    FarmOut,
    FarmUpdate,
    UserCreate,
    UserUpdate,
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


@router.get("/users/{user_id}", response_model=UserOut)
async def get_user(user_id: str, session: AsyncSession = Depends(get_session)) -> UserOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str, req: UserUpdate, session: AsyncSession = Depends(get_session)
) -> UserOut:
    """Settings: change language or display name after setup."""
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(404, "user not found")
    if req.display_name is not None:
        user.display_name = req.display_name
    if req.language_pref is not None:
        user.language_pref = str(getattr(req.language_pref, "value", req.language_pref))
    await session.commit()
    return UserOut.model_validate(user)


@router.patch("/farms/{farm_id}", response_model=FarmOut)
async def rename_farm(
    farm_id: str, req: FarmUpdate, session: AsyncSession = Depends(get_session)
) -> FarmOut:
    """Settings: rename only. Centroid/tier stay derived from setup."""
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    if is_demo_farm(farm):
        # Shared by every device that picked "Try the demo farm"; renaming it
        # would rename it for everyone and hide it from /demo-session.
        raise HTTPException(403, "the shared demo farm cannot be renamed")
    farm.name = req.name
    await session.commit()
    return FarmOut.model_validate(farm)


class DemoSessionOut(BaseModel):
    user: UserOut
    farm: FarmOut
    # Lets the app treat this session as shared: settings that would affect
    # every other device on the demo farm (name, language) stay on-device.
    is_demo: bool = True


class RestoreCodeOut(BaseModel):
    code: str


class RestoreRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)


# Unambiguous alphabet: no 0/O, 1/I/L, so a code read aloud or off a screen
# can be typed back without guessing.
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _new_code() -> str:
    import secrets

    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(9))
    return f"{raw[:3]}-{raw[3:6]}-{raw[6:]}"


def _normalise_code(code: str) -> str:
    raw = "".join(ch for ch in code.upper() if ch.isalnum())
    return f"{raw[:3]}-{raw[3:6]}-{raw[6:]}" if len(raw) == 9 else code.strip().upper()


def is_demo_farm(farm: Farm | None) -> bool:
    return farm is not None and farm.name in DEMO_FARM_NAMES


async def _get_or_create_code(session: AsyncSession, farm: Farm, rotate: bool = False) -> str:
    row = await session.get(FarmRestoreCode, farm.farm_id)
    if row is not None and not rotate:
        return row.code
    code = _new_code()
    while (await session.execute(select(FarmRestoreCode).where(FarmRestoreCode.code == code))).first():
        code = _new_code()
    if row is None:
        session.add(FarmRestoreCode(farm_id=farm.farm_id, code=code))
    else:
        row.code = code
    await session.commit()
    return code


@router.get("/farms/{farm_id}/restore-code", response_model=RestoreCodeOut)
async def get_restore_code(farm_id: str, session: AsyncSession = Depends(get_session)) -> RestoreCodeOut:
    """Shown in Settings on a phone already attached to this farm."""
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    if is_demo_farm(farm):
        raise HTTPException(403, "the shared demo farm has no restore code")
    return RestoreCodeOut(code=await _get_or_create_code(session, farm))


@router.post("/farms/{farm_id}/restore-code/rotate", response_model=RestoreCodeOut)
async def rotate_restore_code(farm_id: str, session: AsyncSession = Depends(get_session)) -> RestoreCodeOut:
    """Cancel a code that was shared by mistake; the old one stops working."""
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    if is_demo_farm(farm):
        raise HTTPException(403, "the shared demo farm has no restore code")
    return RestoreCodeOut(code=await _get_or_create_code(session, farm, rotate=True))


@router.post("/restore", response_model=DemoSessionOut)
async def restore_farm(req: RestoreRequest, session: AsyncSession = Depends(get_session)) -> DemoSessionOut:
    """"Restore my farm" on a new phone: the code maps back to the farm and
    its user, and the phone becomes that farm again -- including, for the
    team's farm, Google Calendar ownership (ownership is keyed on farm_id)."""
    row = (
        await session.execute(select(FarmRestoreCode).where(FarmRestoreCode.code == _normalise_code(req.code)))
    ).scalars().first()
    farm = await session.get(Farm, row.farm_id) if row else None
    user = await session.get(User, farm.user_id) if farm else None
    if farm is None or user is None:
        # One message for every failure: never reveal whether a farm exists.
        raise HTTPException(404, "restore code not recognised")
    return DemoSessionOut(user=UserOut.model_validate(user), farm=FarmOut.model_validate(farm), is_demo=False)


DEMO_FARM_NAMES = ("Kebun Demo PepperDex", "Kebun Demo HuluHilir")


@router.get("/demo-session", response_model=DemoSessionOut)
async def demo_session(session: AsyncSession = Depends(get_session)) -> DemoSessionOut:
    """"Try the demo farm" on first launch: hands the app the seeded,
    already-set-up demo farm (seed/seed.py) instead of creating a new one.
    Shared by every device that picks it -- the alternative, one demo account
    baked into every APK, would also skip the setup wizard for everyone."""
    farm = (
        await session.execute(select(Farm).where(Farm.name.in_(DEMO_FARM_NAMES)).order_by(Farm.name))
    ).scalars().first()
    if farm is None:
        raise HTTPException(404, "demo farm not seeded")
    user = await session.get(User, farm.user_id)
    if user is None:
        raise HTTPException(404, "demo farm has no user")
    return DemoSessionOut(user=UserOut.model_validate(user), farm=FarmOut.model_validate(farm))


@router.get("/farms", response_model=list[FarmOut])
async def list_farms(session: AsyncSession = Depends(get_session)) -> list[FarmOut]:
    """Demo farm discovery only (the v1 Flutter web app at /app/ uses this to
    find it by name). It used to return EVERY farm and its farm_id -- and a
    farm_id is effectively the key to that farm on this account-less API, so
    anyone could read the list and act as any farmer, including the Google
    Calendar owner (closed 2026-09-24). v2 uses GET /demo-session instead."""
    farms = (
        await session.execute(select(Farm).where(Farm.name.in_(DEMO_FARM_NAMES)).order_by(Farm.name))
    ).scalars().all()
    return [FarmOut.model_validate(f) for f in farms]


@router.get("/farms/{farm_id}", response_model=FarmOut)
async def get_farm(farm_id: str, session: AsyncSession = Depends(get_session)) -> FarmOut:
    """Lets the app rehydrate a persisted session against server truth on
    launch, rather than trusting a stale local copy of setup_completed_at."""
    farm = await session.get(Farm, farm_id)
    if farm is None:
        raise HTTPException(404, "farm not found")
    return FarmOut.model_validate(farm)


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

    MINIMAL (no barometer): every distinct pair -- C(n, 2) questions.
    OPTIMISED (barometer): only pairs the sensor cannot separate (Δh < 2.0 m).

    See pairs_needing_farmer_input() for why the minimal path is full
    pairwise rather than the n-1 adjacent comparisons it used to ask.
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
    elevation_conflicts with resolution='farmer' (pepperdex-rules skill §3).
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

    # Enough detail for the app to *show* what was derived rather than
    # silently jumping to the dashboard. On the OPTIMISED path the farmer was
    # asked nothing at all, so without this the most impressive thing the
    # system does -- reconstructing the whole slope from sensor data -- is
    # completely invisible to the person it was done for.
    by_rank = sorted(blocks, key=lambda b: b.elevation_rank)
    derived = []
    for i, b in enumerate(by_rank):
        prev = by_rank[i - 1] if i > 0 else None
        drop = None
        if prev is not None and b.baro_rel_m is not None and prev.baro_rel_m is not None:
            drop = round(prev.baro_rel_m - b.baro_rel_m, 1)
        derived.append({
            "block_id": b.block_id,
            "label": b.label,
            "elevation_rank": b.elevation_rank,
            "baro_rel_m": b.baro_rel_m,
            # Metres of fall from the block immediately above it.
            "drop_from_above_m": drop,
        })

    return {
        "ranks": ranks,
        "edges_created": len(edges),
        "conflicts_logged": len(conflicts),
        "setup_completed": True,
        # True when the ordering came entirely from the sensor -- no question
        # was put to the farmer. This is what makes the summary worth showing.
        "derived_automatically": not farmer_pairs and baro is not None,
        "questions_answered": len(farmer_pairs),
        "blocks": derived,
    }


@router.get("/blocks/{block_id}/detail")
async def block_detail(block_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Everything the terrain profile card needs about one block.

    Kept separate from the dashboard payload deliberately: photo URIs, voice
    labels and the full observation history are only wanted when a farmer
    actually taps a block, and folding them into the dashboard would make the
    landing request heavier for every user on a slow connection.

    Returns no ownership or boundary data (pepperdex-rules §4) -- a block is a
    label, a point, and a rank.
    """
    from app.models.diagnosis import Diagnosis, Observation

    block = await session.get(Block, block_id)
    if block is None:
        raise HTTPException(404, "block not found")

    rows = (
        await session.execute(
            select(Observation, Diagnosis)
            .outerjoin(Diagnosis, Diagnosis.observation_id == Observation.observation_id)
            .where(Observation.block_id == block_id)
            .order_by(Observation.captured_at.desc())
            .limit(20)
        )
    ).all()

    history = [
        {
            "observation_id": obs.observation_id,
            "image_uri": obs.image_uri,
            "capture_target": obs.capture_target,
            "captured_at": obs.captured_at.isoformat(),
            "predicted_class": diag.predicted_class if diag else None,
            "confidence": diag.confidence if diag else None,
            # WHICH model decided. Without it an aggregate over diagnoses
            # silently mixes the CNN and the vision backend, and a count of
            # "classes ever produced" says nothing about either one.
            "model_version": diag.model_version if diag else None,
            # Surfaced so the card can show uncertainty rather than assert a
            # class the model was not confident about (pepperdex-rules §9).
            "below_threshold": (diag.confidence < 0.60) if diag else None,
        }
        for obs, diag in rows
    ]

    # The block's own capture photo is the natural header, but seeded blocks
    # carry a placeholder path that resolves to nothing -- which is why the
    # demo farm showed a blank header. Fall back to the most recent real
    # observation photo, which is both a valid image and a more current view
    # of the block than the day it was marked.
    header = block.photo_uri
    if not header or header.startswith("seed/"):
        header = next((h["image_uri"] for h in history if h["image_uri"]), None)

    return {
        "block_id": block.block_id,
        "label": block.label,
        "photo_uri": block.photo_uri,
        "header_image_uri": header,
        # An audio sticker, replayed beside the photo. Never transcribed --
        # there is no ASR anywhere in this codebase (pepperdex-rules §1).
        "voice_label_uri": block.voice_label_uri,
        "elevation_rank": block.elevation_rank,
        "drainage": block.drainage,
        "vine_count": block.vine_count,
        "current_state": block.current_state,
        "baro_rel_m": block.baro_rel_m,
        "marked_at": block.marked_at.isoformat() if block.marked_at else None,
        "observations": history,
    }
