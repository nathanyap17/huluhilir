"""Farm memory for the Advisor: a factual snapshot of THIS farm, read from the
database each time a question is asked.

Before this, the Advisor saw only the question text -- "does this mean the
blocks are safer now?" reached it with no farm, no blocks, no diagnoses, so it
asked the farmer what crop they grow (observed 2026-09-24). Everything below
is a row the app already stores; nothing is inferred or summarised by a model.

Deliberately excluded (rules 2 and 4): doses and product names (the Priority
card shows those from the rules table), land boundaries, owner details of
neighbouring blocks.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun, CalendarEventProposal, Recommendation
from app.models.base import KUCHING_TZ, now_kuching
from app.models.core import Block, Farm
from app.models.diagnosis import Diagnosis, DiagnosisCycle, Observation, RiskAssessment
from app.tools.advisor import should_diagnose
from app.tools.weather import get_weather

_STATE_EN = {"protected": "Protected", "alerted": "Alerted", "harmed": "Harmed", "overrun": "Overrun"}


def _d(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    if dt.tzinfo is not None:
        dt = dt.astimezone(KUCHING_TZ)
    return dt.strftime("%a %d %b %Y %H:%M")


async def build_farm_context(session: AsyncSession, farm_id: str) -> str:
    farm = await session.get(Farm, farm_id)
    if farm is None:
        return ""
    blocks = (
        await session.execute(
            select(Block).where(Block.farm_id == farm_id, Block.is_external.is_(False)).order_by(Block.elevation_rank)
        )
    ).scalars().all()
    labels = {b.block_id: b.label for b in blocks}
    # Last two completed cycles, dated by the server clock. (Photo times are
    # correct since the KuchingDateTime fix, but a cycle's completion time is
    # the natural "when was this diagnosis" for the farmer.)
    cycles = (
        await session.execute(
            select(DiagnosisCycle)
            .where(DiagnosisCycle.farm_id == farm_id, DiagnosisCycle.status == "complete")
            .order_by(DiagnosisCycle.completed_at.desc())
            .limit(2)
        )
    ).scalars().all()

    lines = [
        f"Farm: {farm.name} (black pepper). Today: {_d(now_kuching())}. "
        f"Elevation detection: {farm.elevation_tier}. {len(blocks)} blocks, listed upslope (rank 1) to downslope.",
        "",
        "BLOCKS -- current state, then the result from the latest and the previous diagnosis cycle.",
        "(An 'unrelated' photo or a low-confidence result is not evidence, so it does not change a block's state.)",
    ]
    for b in blocks:
        per_cycle = []
        for label, c in zip(("latest", "previous"), cycles):
            d = (
                await session.execute(
                    select(Diagnosis)
                    .join(Observation, Observation.observation_id == Diagnosis.observation_id)
                    .where(Observation.block_id == b.block_id, Diagnosis.cycle_id == c.cycle_id)
                    .order_by(Observation.captured_at.desc())
                    .limit(1)
                )
            ).scalars().first()
            if d is not None:
                low = " (low confidence)" if d.below_threshold else ""
                per_cycle.append(f"{label} cycle {_d(c.completed_at)}: {d.predicted_class} {round(d.confidence * 100)}%{low}")
        changed = f", state since {_d(b.state_changed_at)}" if b.state_changed_at else ""
        lines.append(
            f"- {b.label} (elevation rank {b.elevation_rank}, drainage {b.drainage}): "
            f"{_STATE_EN.get(b.current_state, b.current_state)}{changed}. "
            + ("; ".join(per_cycle) if per_cycle else "never diagnosed") + "."
        )

    run = (
        await session.execute(
            select(AgentRun)
            .join(Recommendation, Recommendation.run_id == AgentRun.run_id)
            .where(AgentRun.farm_id == farm_id)
            .order_by(AgentRun.started_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if run is not None:
        recs = (
            await session.execute(
                select(Recommendation).where(Recommendation.run_id == run.run_id).order_by(Recommendation.sequence)
            )
        ).scalars().all()
        how = "rules table only (AI model fell back)" if run.status == "partial" else "AI agent arbitration"
        lines += ["", f"LATEST ACTION PLAN (decided {_d(run.started_at)} by {how}):"]
        for r in recs:
            defer = f", deferred: {r.defer_cause}" if r.defer_cause else ""
            lines.append(f"{r.sequence}. {r.action_type} on {labels.get(r.block_id, '?')} at {_d(r.recommended_at)}{defer}")
        risks = (
            await session.execute(
                select(RiskAssessment).where(RiskAssessment.run_id == run.run_id).order_by(RiskAssessment.risk_score.desc())
            )
        ).scalars().all()
        if risks:
            lines += ["", "PROJECTED DOWNHILL SPREAD from that run (estimates, not measurements):"]
            for rk in risks[:6]:
                eta = f", may arrive in ~{rk.eta_days} days" if rk.eta_days else ""
                lines.append(
                    f"- {labels.get(rk.source_block_id, '?')} -> {labels.get(rk.block_id, '?')}: "
                    f"risk {round(rk.risk_score * 100)}% ({rk.risk_band}){eta}, confidence {round(rk.confidence * 100)}%"
                )

    proposals = (
        await session.execute(
            select(CalendarEventProposal)
            .where(CalendarEventProposal.farm_id == farm_id, CalendarEventProposal.status != "superseded")
            .order_by(CalendarEventProposal.created_at.desc())
            .limit(4)
        )
    ).scalars().all()
    if proposals:
        lines += ["", "CALENDAR PROPOSALS:"]
        lines += [f"- {p.title} at {_d(p.start_time)}: {p.status}" for p in proposals]

    weather = get_weather(farm_id)
    past = sum(o.rainfall_mm for o in weather.rainfall_7d)
    ahead = sum(f.rainfall_mm for f in weather.forecast_7d)
    pulses = [f"{f.forecast_date} ~{f.rainfall_mm:.0f}mm" for f in weather.forecast_7d if f.rainfall_mm >= 20]
    lines += [
        "",
        f"RAIN: last 7 days ~{past:.0f} mm, next 7 days ~{ahead:.0f} mm"
        + (f"; heavy days: {', '.join(pulses)}" if pulses else "")
        + (" (cached estimate, live weather unavailable)" if weather.is_cached_fallback else " (data.gov.my forecast)"),
    ]

    verdict = await should_diagnose(
        session, farm_id,
        rain_48h_mm=sum(o.rainfall_mm for o in weather.rainfall_7d[:2]),
        rain_since_last_cycle_mm=past,
    )
    lines.append(
        f"ADVISOR VERDICT (should the farmer diagnose again?): urgency {verdict.urgency}, "
        f"reason: {verdict.reason_ms}; days since last cycle: {verdict.days_since_last_cycle}."
    )
    return "\n".join(lines)
