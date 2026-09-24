"""should_diagnose() -- the Advisor's deterministic core. docs/PROJECT_SPEC.md §6.

Computed at request time (GET /farm/{id}/advisor); no background polling
(pepperdex-rules skill §6: the Advisor recommends, it never blocks, and must
work with zero diagnosis cycles ever having existed).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import now_kuching
from app.models.core import Block
from app.models.diagnosis import DiagnosisCycle
from app.schemas.advisor import AdvisorVerdictOut
from app.schemas.enums import AdvisorUrgency

HEAVY_RAIN_MM = 30.0
STABLE_RAIN_CEILING_MM = 20.0
STABLE_DAYS_CEILING = 14
STALE_DAYS = 21
INCUBATION_FLOOR_DAYS = 3
ACTIVE_INFECTION_FLOOR_DAYS = 5

_REASON_TEXT_MS = {
    "heavy_rain_recent": "Hujan lebat baru-baru ini. Masa untuk diagnosis.",
    "active_infection": "Jangkitan aktif dikesan. Diagnosis susulan disyorkan.",
    "monitoring_infection": "Jangkitan aktif sedang dipantau. Ikuti tindakan keutamaan di atas.",
    "protected_stable": "Semua blok sihat dan hujan rendah. Tiada diagnosis diperlukan buat masa ini.",
    "stale": "Sudah lama sejak diagnosis terakhir. Pertimbangkan pusingan baharu.",
    "no_action_needed": "Tiada tindakan diperlukan buat masa ini.",
}


async def should_diagnose(
    session: AsyncSession, farm_id: str, rain_48h_mm: float, rain_since_last_cycle_mm: float
) -> AdvisorVerdictOut:
    blocks = (await session.execute(select(Block).where(Block.farm_id == farm_id))).scalars().all()
    non_external = [b for b in blocks if not b.is_external]
    blocks_all_protected = bool(non_external) and all(b.current_state == "protected" for b in non_external)
    any_alerted_or_harmed = any(b.current_state in ("alerted", "harmed") for b in non_external)

    last_cycle = (
        await session.execute(
            select(DiagnosisCycle)
            .where(DiagnosisCycle.farm_id == farm_id, DiagnosisCycle.status == "complete")
            .order_by(DiagnosisCycle.completed_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    now = now_kuching()
    if last_cycle is not None and last_cycle.completed_at is not None:
        # SQLite drops tzinfo on read even for DateTime(timezone=True) columns,
        # so completed_at comes back naive; subtracting it from an aware
        # now_kuching() raised TypeError -> dashboard 500 right after the
        # first diagnosis (2026-09-20). Values are stored as Asia/Kuching.
        completed_at = last_cycle.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=now.tzinfo)
        days_since = (now - completed_at).days
        last_cycle_at = completed_at
    else:
        # Never diagnosed -- treat as maximally stale so a never-diagnosed farm
        # eventually gets nudged toward its first cycle, rather than silently
        # never recommending one (pepperdex-rules skill §6 requires the app to
        # work with zero photos, not that the Advisor stay silent forever).
        days_since = STALE_DAYS
        last_cycle_at = None

    if rain_48h_mm >= HEAVY_RAIN_MM and days_since >= INCUBATION_FLOOR_DAYS:
        urgency, reason_code = AdvisorUrgency.high, "heavy_rain_recent"
    elif any_alerted_or_harmed and days_since >= ACTIVE_INFECTION_FLOOR_DAYS:
        urgency, reason_code = AdvisorUrgency.high, "active_infection"
    elif any_alerted_or_harmed and days_since < ACTIVE_INFECTION_FLOOR_DAYS:
        urgency, reason_code = AdvisorUrgency.medium, "monitoring_infection"
    elif blocks_all_protected and rain_since_last_cycle_mm < STABLE_RAIN_CEILING_MM and days_since < STABLE_DAYS_CEILING:
        urgency, reason_code = AdvisorUrgency.low, "protected_stable"
    elif days_since >= STALE_DAYS:
        urgency, reason_code = AdvisorUrgency.medium, "stale"
    else:
        urgency, reason_code = AdvisorUrgency.none, "no_action_needed"

    return AdvisorVerdictOut(
        farm_id=farm_id,
        urgency=urgency,
        reason_code=reason_code,
        reason_ms=_REASON_TEXT_MS.get(reason_code, _REASON_TEXT_MS["no_action_needed"]),
        last_cycle_at=last_cycle_at,
        days_since_last_cycle=days_since,
        rain_since_last_cycle_mm=rain_since_last_cycle_mm,
        blocks_all_protected=blocks_all_protected,
        computed_at=now,
    )
