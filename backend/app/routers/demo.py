"""Admin control of the shared demo farm: capture a snapshot, restore it.

Gated by the restore code of the team's own farm (the Google Calendar owner,
CALENDAR_OWNER_FARM_ID). Only the admin phone can see that code (Settings),
so no separate admin password or secret is needed. Usable from the phone's
browser via the interactive API docs (/docs).
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.core import DemoSnapshot, FarmRestoreCode
from app.routers.setup import _normalise_code
from app.tools import demo_snapshot
from app.tools.calendar_service import get_calendar_owner

router = APIRouter(prefix="/demo", tags=["demo"])


class AdminCode(BaseModel):
    restore_code: str


class SnapshotStatus(BaseModel):
    exists: bool
    captured_at: Optional[datetime] = None
    restored_at: Optional[datetime] = None
    next_nightly_restore_in_s: float


class SnapshotResult(BaseModel):
    rows: dict[str, int]


async def _require_admin(body: AdminCode, session: AsyncSession) -> None:
    owner = get_calendar_owner()
    if not owner:
        raise HTTPException(403, "no admin farm is configured")
    row = (
        await session.execute(select(FarmRestoreCode).where(FarmRestoreCode.farm_id == owner))
    ).scalar_one_or_none()
    if row is None or row.code != _normalise_code(body.restore_code):
        raise HTTPException(403, "not the admin farm's restore code")


@router.get("/snapshot", response_model=SnapshotStatus)
async def snapshot_status(session: AsyncSession = Depends(get_session)) -> SnapshotStatus:
    snap = await session.get(DemoSnapshot, demo_snapshot.SNAPSHOT_ID)
    return SnapshotStatus(
        exists=snap is not None,
        captured_at=snap.captured_at if snap else None,
        restored_at=snap.restored_at if snap else None,
        next_nightly_restore_in_s=round(demo_snapshot.seconds_until_next(demo_snapshot.NIGHTLY_HOUR)),
    )


@router.post("/snapshot", response_model=SnapshotResult)
async def capture_snapshot(body: AdminCode, session: AsyncSession = Depends(get_session)) -> SnapshotResult:
    """Freeze the demo farm as it is now (replaces any earlier snapshot)."""
    await _require_admin(body, session)
    try:
        return SnapshotResult(rows=await demo_snapshot.capture(session))
    except LookupError as exc:
        raise HTTPException(404, str(exc))


@router.post("/restore", response_model=SnapshotResult)
async def restore_snapshot(body: AdminCode, session: AsyncSession = Depends(get_session)) -> SnapshotResult:
    """Put the demo farm back to the snapshot now (e.g. before a judging slot)."""
    await _require_admin(body, session)
    try:
        return SnapshotResult(rows=await demo_snapshot.restore(session))
    except LookupError as exc:
        raise HTTPException(404, str(exc))
