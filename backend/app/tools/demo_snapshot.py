"""Snapshot and restore of the shared demo farm.

Every phone that picks "Try the demo farm" is attached to ONE farm, so a
visitor's photos, runs and approvals change it for everyone after them. At a
booth that drifts into a mess. The admin freezes the farm in a good state
(`capture`), and `restore` puts it back: nightly, and on demand before a
judging slot.

Restore keeps the same farm_id and user_id, so phones already on the demo
farm keep working; they simply see the restored state on their next refresh.
Only rows that belong to the demo farm are touched. Global tables (treatment
rules, knowledge, speech, weather) and every other farm are never read or
written here.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base
from app.models.base import KUCHING_TZ, now_kuching
from app.models.core import DemoSnapshot, Farm

logger = logging.getLogger(__name__)

SNAPSHOT_ID = "demo"
NIGHTLY_HOUR = 3  # 03:00 Asia/Kuching, when the booth is closed

# Parents before children: the insert order. Deletion runs in reverse.
TABLE_ORDER = [
    "walk_sessions",
    "walk_samples",
    "blocks",
    "diagnosis_cycles",
    "agent_runs",
    "advisor_verdicts",
    "calendar_sync_grants",
    "elevation_conflicts",
    "flow_edges",
    "observations",
    "diagnoses",
    "risk_assessments",
    "treatment_applications",
    "alerts",
    "council_debates",
    "recommendations",
    "calendar_event_proposals",
]

# Farm columns a restore puts back. farm_id and user_id never change.
FARM_FIELDS_SKIPPED = {"farm_id", "user_id"}


def _t(name: str):
    return Base.metadata.tables[name]


# ---------------------------------------------------------------- encoding --

def _encode(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$date": value.isoformat()}
    if isinstance(value, Decimal):
        return float(value)
    return value


def _decode(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        if "$dt" in value:
            return datetime.fromisoformat(value["$dt"])
        if "$date" in value:
            return date.fromisoformat(value["$date"])
    return value


def _encode_row(row: dict) -> dict:
    return {k: _encode(v) for k, v in row.items()}


def _decode_row(row: dict) -> dict:
    return {k: _decode(v) for k, v in row.items()}


# ---------------------------------------------------------------- selection --

async def _ids(session: AsyncSession, table: str, column: str, where) -> set:
    t = _t(table)
    return set((await session.execute(select(t.c[column]).where(where))).scalars().all())


async def _farm_rows(session: AsyncSession, farm_id: str) -> dict[str, list[dict]]:
    """Every row that belongs to the farm, keyed by table, in TABLE_ORDER."""
    walk_ids = await _ids(session, "walk_sessions", "walk_session_id", _t("walk_sessions").c.farm_id == farm_id)
    block_ids = await _ids(session, "blocks", "block_id", _t("blocks").c.farm_id == farm_id)
    run_ids = await _ids(session, "agent_runs", "run_id", _t("agent_runs").c.farm_id == farm_id)
    obs_ids = await _ids(session, "observations", "observation_id", _t("observations").c.block_id.in_(block_ids))

    def by(table: str):
        c = _t(table).c
        if table in ("walk_sessions", "blocks", "diagnosis_cycles", "agent_runs", "advisor_verdicts",
                     "calendar_sync_grants", "elevation_conflicts", "flow_edges", "calendar_event_proposals"):
            return c.farm_id == farm_id
        if table == "walk_samples":
            return c.walk_session_id.in_(walk_ids)
        if table in ("observations", "treatment_applications", "risk_assessments"):
            return c.block_id.in_(block_ids)
        if table == "diagnoses":
            return c.observation_id.in_(obs_ids)
        if table in ("alerts", "council_debates"):
            return c.run_id.in_(run_ids)
        if table == "recommendations":
            return or_(c.run_id.in_(run_ids), c.block_id.in_(block_ids))
        raise KeyError(table)

    out: dict[str, list[dict]] = {}
    for table in TABLE_ORDER:
        rows = (await session.execute(select(_t(table)).where(by(table)))).mappings().all()
        out[table] = [dict(r) for r in rows]
    return out


# ---------------------------------------------------------------- public API --

async def find_demo_farm(session: AsyncSession) -> Farm | None:
    from app.routers.setup import DEMO_FARM_NAMES  # avoid an import cycle at module load

    return (
        await session.execute(select(Farm).where(Farm.name.in_(DEMO_FARM_NAMES)).order_by(Farm.name))
    ).scalars().first()


async def capture(session: AsyncSession) -> dict[str, int]:
    """Freeze the demo farm as it is now. Replaces any earlier snapshot."""
    farm = await find_demo_farm(session)
    if farm is None:
        raise LookupError("demo farm not seeded")
    rows = await _farm_rows(session, farm.farm_id)
    farm_row = dict((await session.execute(select(_t("farms")).where(_t("farms").c.farm_id == farm.farm_id))).mappings().one())
    payload = {
        "farm_id": farm.farm_id,
        "farm": _encode_row(farm_row),
        "tables": {name: [_encode_row(r) for r in rs] for name, rs in rows.items()},
    }
    snap = await session.get(DemoSnapshot, SNAPSHOT_ID)
    if snap is None:
        session.add(DemoSnapshot(snapshot_id=SNAPSHOT_ID, payload=payload, captured_at=now_kuching()))
    else:
        snap.payload = payload
        snap.captured_at = now_kuching()
    await session.commit()
    return {name: len(rs) for name, rs in rows.items() if rs}


async def restore(session: AsyncSession) -> dict[str, int]:
    """Put the demo farm back to the snapshot, in one transaction."""
    snap = await session.get(DemoSnapshot, SNAPSHOT_ID)
    if snap is None:
        raise LookupError("no demo snapshot has been captured")
    farm = await find_demo_farm(session)
    if farm is None or farm.farm_id != snap.payload["farm_id"]:
        raise LookupError("the demo farm no longer matches the snapshot")
    farm_id = farm.farm_id

    # farms.walk_session_id points at walk_sessions: release it before deleting them.
    await session.execute(update(_t("farms")).where(_t("farms").c.farm_id == farm_id).values(walk_session_id=None))

    current = await _farm_rows(session, farm_id)
    for table in reversed(TABLE_ORDER):
        rows = current[table]
        if not rows:
            continue
        t = _t(table)
        pk = list(t.primary_key.columns)[0]
        ids = [r[pk.name] for r in rows]
        for i in range(0, len(ids), 500):
            await session.execute(delete(t).where(pk.in_(ids[i:i + 500])))

    restored: dict[str, int] = {}
    for table in TABLE_ORDER:
        rows = [_decode_row(r) for r in snap.payload["tables"].get(table, [])]
        if rows:
            await session.execute(insert(_t(table)), rows)
            restored[table] = len(rows)

    farm_values = {
        k: v for k, v in _decode_row(snap.payload["farm"]).items() if k not in FARM_FIELDS_SKIPPED
    }
    await session.execute(update(_t("farms")).where(_t("farms").c.farm_id == farm_id).values(**farm_values))
    snap.restored_at = now_kuching()
    await session.commit()
    return restored


def seconds_until_next(hour: int, now: datetime | None = None) -> float:
    now = (now or datetime.now(KUCHING_TZ)).astimezone(KUCHING_TZ)
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def nightly_restore_loop(session_factory) -> None:
    """Restore the demo farm every night at NIGHTLY_HOUR (Kuching), if a
    snapshot exists. Runs for the life of the server process (Cloud Run keeps
    one instance with CPU always allocated). A failure is logged, never fatal."""
    while True:
        await asyncio.sleep(seconds_until_next(NIGHTLY_HOUR))
        try:
            async with session_factory() as session:
                if await session.get(DemoSnapshot, SNAPSHOT_ID) is not None:
                    counts = await restore(session)
                    logger.info("nightly demo restore: %s", counts)
        except Exception:  # keep the loop alive for tomorrow
            logger.exception("nightly demo restore failed")
