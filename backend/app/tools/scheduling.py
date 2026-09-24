"""Turning a recommendation into a calendar slot a farmer can actually use.

Before (observed 2026-09-24): a "clear the drain now" proposal started at the
current minute (3:00 pm now -> 3-4 pm), and a spray/drench on a rain-free DAY
started at 00:00, because find_spray_window works in whole forecast days.
Rules here:
  * a date-only time (00:00) means "that day" -> 08:00, morning field work;
  * never sooner than the next full hour at least 30 min from now;
  * field hours only: a start after 17:00 moves to 08:00 the next day, a
    start before 07:00 moves to 08:00 the same day.
This only chooses the hour. The DAY still comes from the rules table / spray
window (rule 2): moving within the same day or to the next morning never
makes a start earlier than the window allowed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import CalendarEventProposal
from app.models.base import KUCHING_TZ, now_kuching
from app.models.core import Block

SCHEDULABLE = ("spray", "drench", "clear_drain")
MORNING_HOUR = 8
EARLIEST_HOUR = 7
LATEST_START_HOUR = 17
SLOT = timedelta(hours=1)

_ACTION_MS = {
    "spray": "Semburan Racun Kulat",
    "drench": "Siraman Fungisida Pangkal",
    "clear_drain": "Pembersihan Parit Saliran",
}


def _naive_kuching(dt: datetime) -> datetime:
    return dt.astimezone(KUCHING_TZ).replace(tzinfo=None) if dt.tzinfo else dt


def workable_slot(when: datetime, now: Optional[datetime] = None) -> datetime:
    """The start of a 1-hour field slot on or after `when` (naive Kuching)."""
    when = _naive_kuching(when)
    now = _naive_kuching(now or now_kuching())
    if (when.hour, when.minute, when.second) == (0, 0, 0):
        when = when.replace(hour=MORNING_HOUR)
    soonest = now + timedelta(minutes=30)
    soonest = soonest.replace(minute=0, second=0, microsecond=0) + (
        timedelta(hours=1) if (soonest.minute or soonest.second or soonest.microsecond) else timedelta(0)
    )
    start = max(when, soonest).replace(second=0, microsecond=0)
    if start.hour < EARLIEST_HOUR:
        start = start.replace(hour=MORNING_HOUR, minute=0)
    if start.hour > LATEST_START_HOUR or (start.hour == LATEST_START_HOUR and start.minute > 0):
        start = (start + timedelta(days=1)).replace(hour=MORNING_HOUR, minute=0)
    return start


def proposal_for(
    *,
    farm_id: str,
    run_id: Optional[str],
    recommendation_id: str,
    block: Optional[Block],
    action_type: str,
    start: datetime,
    reason_ms: str,
) -> CalendarEventProposal:
    label = block.label if block else "?"
    return CalendarEventProposal(
        farm_id=farm_id,
        run_id=run_id,
        recommendation_id=recommendation_id,
        title=f"Rawatan: {_ACTION_MS.get(action_type, action_type.capitalize())} - {label}",
        start_time=start,
        end_time=start + SLOT,
        description=f"{reason_ms} (Disyorkan oleh PepperDex AI)",
        location=f"Blok {label}, Ladang Lada",
        status="pending_approval",
        approved_by_farmer=False,
    )


async def pending_proposal_for_recommendation(
    session: AsyncSession, recommendation_id: str
) -> Optional[CalendarEventProposal]:
    return (
        await session.execute(
            select(CalendarEventProposal)
            .where(
                CalendarEventProposal.recommendation_id == recommendation_id,
                CalendarEventProposal.status == "pending_approval",
            )
            .order_by(CalendarEventProposal.created_at.desc())
        )
    ).scalars().first()
