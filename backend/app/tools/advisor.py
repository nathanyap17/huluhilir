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


# ---------------------------------------------------------------------------
# Next best check (2026-09-27). should_diagnose() answers "is a check due
# NOW?"; this answers "WHEN is the next check most useful?", so the farmer
# doesn't photograph every block when nothing has changed.
#
# Deterministic, from the farm's own data:
#   * rain pulses in the forecast -- the knowledge base: "inspect a few days
#     after heavy rain, because that is when new infections happen" (kb_051;
#     also kb_011, kb_020);
#   * approved treatments -- re-check once the treatment has had its
#     rain-fast period (from the rulebook) and a few days to act;
#   * block states and time since the last check (the same floors as above).
# ---------------------------------------------------------------------------

HEAVY_DAY_MM = 20.0        # a forecast day that can drive new infection
DAYS_AFTER_PULSE = 2       # "a few days after heavy rain" (kb_051) -- design choice
DAYS_AFTER_TREATMENT = 3   # after the rain-fast period, let the treatment act
ROUTINE_DAYS = {"infected": ACTIVE_INFECTION_FLOOR_DAYS, "protected": STABLE_DAYS_CEILING, "other": 7}


def _fmt(d) -> tuple[str, str]:
    days_ms = ["Isnin", "Selasa", "Rabu", "Khamis", "Jumaat", "Sabtu", "Ahad"]
    days_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    return f"{days_ms[d.weekday()]} {d.day}/{d.month}", f"{days_en[d.weekday()]} {d.day}/{d.month}"


async def next_best_check(
    session: AsyncSession,
    farm_id: str,
    verdict: AdvisorVerdictOut,
    forecast: list[tuple[object, float]],
) -> AdvisorVerdictOut:
    """Fill verdict.suggested_date / days_until_recommended and a bilingual
    reason. `forecast` is [(date or ISO string, rainfall_mm), ...] for the
    coming days. Never raises: with no data it falls back to the routine
    interval. The farmer may always check sooner (rule: the Advisor never
    blocks a diagnosis)."""
    from datetime import date as _date, datetime as _dt, timedelta

    from app.models.agent import CalendarEventProposal, Recommendation
    from app.models.knowledge import TreatmentOption

    today = verdict.computed_at.date()

    def as_date(v):
        if isinstance(v, _dt):
            return v.date()
        if isinstance(v, _date):
            return v
        return _date.fromisoformat(str(v)[:10])

    # Not sooner than the incubation floor after the last check.
    floor = today
    if verdict.last_cycle_at is not None:
        floor = max(today, verdict.last_cycle_at.date() + timedelta(days=INCUBATION_FLOOR_DAYS))

    candidates: list[tuple[_date, str, str, str]] = []  # (date, basis, ms, en)

    if str(getattr(verdict.urgency, "value", verdict.urgency)) == "high":
        candidates.append((today, "due_now", "Periksa hari ini: " + verdict.reason_ms,
                           "Check today: a check is due now."))

    pulse_days = sorted(as_date(d) for d, mm in forecast if mm >= HEAVY_DAY_MM and as_date(d) >= today)
    if pulse_days:
        pulse = pulse_days[0]
        p_ms, p_en = _fmt(pulse)
        candidates.append((
            pulse + timedelta(days=DAYS_AFTER_PULSE), "rain_pulse",
            f"Hujan lebat dijangka {p_ms}. Periksa {DAYS_AFTER_PULSE} hari selepas itu, apabila jangkitan baharu berlaku.",
            f"Heavy rain is expected {p_en}. Check {DAYS_AFTER_PULSE} days after, when new infections happen.",
        ))

    # Approved (or synced) sprays/drenches: re-check after rain-fast + a few days.
    rows = (
        await session.execute(
            select(CalendarEventProposal, Recommendation, TreatmentOption)
            .join(Recommendation, CalendarEventProposal.recommendation_id == Recommendation.recommendation_id)
            .outerjoin(TreatmentOption, Recommendation.treatment_id == TreatmentOption.treatment_id)
            .where(
                CalendarEventProposal.farm_id == farm_id,
                CalendarEventProposal.status.in_(("approved", "deployed")),
                Recommendation.action_type.in_(("spray", "drench")),
            )
        )
    ).all()
    for proposal, rec, treatment in rows:
        start = as_date(proposal.start_time)
        if start < today - timedelta(days=DAYS_AFTER_TREATMENT):
            continue  # an old treatment; its follow-up window has passed
        rainfast_days = -(-((treatment.rainfast_hours if treatment else None) or 0) // 24)
        when = start + timedelta(days=rainfast_days + DAYS_AFTER_TREATMENT)
        s_ms, s_en = _fmt(start)
        candidates.append((
            when, "treatment_follow_up",
            f"Rawatan dijadualkan {s_ms}. Periksa semula selepas ia sempat berkesan.",
            f"A treatment is scheduled for {s_en}. Re-check once it has had time to work.",
        ))

    # Routine interval from the last check, by the farm's current state.
    if verdict.last_cycle_at is None:
        candidates.append((today, "first_check", "Belum ada diagnosis. Periksa bila-bila masa untuk bermula.",
                           "No check yet. Start whenever you're ready."))
    else:
        state = ("infected" if verdict.reason_code in ("active_infection", "monitoring_infection")
                 else "protected" if verdict.blocks_all_protected else "other")
        when = verdict.last_cycle_at.date() + timedelta(days=ROUTINE_DAYS[state])
        candidates.append((
            when, "routine",
            "Jangkitan aktif: periksa susulan." if state == "infected" else "Pemeriksaan rutin mengikut keadaan ladang.",
            "Active infection: follow-up check." if state == "infected" else "Routine check for your farm's condition.",
        ))

    chosen = min(candidates, key=lambda c: max(c[0], floor))
    suggested = max(chosen[0], floor)
    s_ms, s_en = _fmt(suggested)
    if suggested == today:
        when_ms, when_en = "hari ini", "today"
    else:
        when_ms, when_en = s_ms, s_en

    verdict.suggested_date = suggested
    verdict.days_until_recommended = (suggested - today).days
    verdict.next_check_basis = chosen[1]
    verdict.next_check_ms = f"Pemeriksaan seterusnya: {when_ms}. {chosen[2]}"[:300]
    verdict.next_check_en = f"Next check: {when_en}. {chosen[3]}"[:300]
    return verdict
