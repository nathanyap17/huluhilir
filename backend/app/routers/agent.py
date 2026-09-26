import asyncio
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.agent import progress
from app.agent.runner import run_advisor_question, run_root_agent
from app.config import settings
from app.db import get_session
from app.models.agent import AgentRun, CalendarEventProposal, CouncilDebate, Recommendation
from app.models.core import Block
from app.schemas.advisor import AdvisorVerdictOut
from app.schemas.agent import AgentRunOut
from app.tools.advisor import next_best_check, should_diagnose
from app.tools.weather import get_weather

router = APIRouter(tags=["agent"])


class AgentRunRequest(BaseModel):
    farm_id: str
    message: str
    cycle_id: Optional[str] = None
    trigger: str = "manual"
    # True: return the run row immediately (status "running") and do the work
    # in the background; the app polls GET /agent/runs/{run_id}/events and
    # shows each agent's step in the Advisor chat instead of a blind spinner.
    background: bool = False


logger = logging.getLogger(__name__)
_BACKGROUND_TASKS: set[asyncio.Task] = set()


async def _run_in_background(run_id: str, req: AgentRunRequest) -> None:
    async with db.SessionLocal() as session:
        try:
            await run_root_agent(
                session, req.farm_id, req.message, cycle_id=req.cycle_id,
                trigger=req.trigger, agent_run_id=run_id,
            )
            await session.commit()
            progress.finish(run_id, "done")
        except Exception as exc:  # never leave the client polling forever
            logger.exception("background agent run %s failed", run_id)
            await session.rollback()
            row = await session.get(AgentRun, run_id)
            if row is not None:
                row.status = "failed"
                await session.commit()
            progress.emit(run_id, "root_agent", f"Analisis gagal: {type(exc).__name__}. Cuba lagi.",
                          f"Analysis failed: {type(exc).__name__}. Please retry.", kind="warning")
            progress.finish(run_id, "failed")


@router.post("/agent/run", response_model=AgentRunOut)
async def agent_run(req: AgentRunRequest, session: AsyncSession = Depends(get_session)) -> AgentRunOut:
    if req.background:
        row = AgentRun(
            farm_id=req.farm_id, trigger=req.trigger, cycle_id=req.cycle_id, tools_called=[],
            llm_model=settings.litellm_model, status="running",
        )
        session.add(row)
        await session.commit()
        progress.start(row.run_id)
        task = asyncio.create_task(_run_in_background(row.run_id, req))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return AgentRunOut.model_validate(row)

    agent_run_row = await run_root_agent(
        session, req.farm_id, req.message, cycle_id=req.cycle_id, trigger=req.trigger
    )
    await session.commit()
    progress.finish(agent_run_row.run_id, "done")
    return AgentRunOut.model_validate(agent_run_row)


async def _rebuild_events(session: AsyncSession, run: AgentRun) -> list[dict[str, Any]]:
    """Feed for a run that is no longer in memory (server restarted, or an old
    run reopened) -- rebuilt only from what was persisted, never re-inferred."""
    blocks = (await session.execute(select(Block).where(Block.farm_id == run.farm_id))).scalars().all()
    labels = {b.block_id: b.label for b in blocks}
    events: list[dict[str, Any]] = []

    debate = (await session.execute(select(CouncilDebate).where(CouncilDebate.run_id == run.run_id))).scalars().first()
    if debate is not None:
        for turn in debate.transcript or []:
            if turn.get("argument"):
                key = progress.COUNCIL_AGENT.get(turn.get("agent", ""), "council_orchestrator")
                events.append(progress.event(key, turn["argument"], turn["argument"], "debate"))

    for call in run.tools_called or []:
        if call.get("name") in ("deterministic_fallback", "rules_guard"):
            ev = progress.describe_call(call, labels)
            if ev:
                events.append(ev)

    recs = (
        await session.execute(select(Recommendation).where(Recommendation.run_id == run.run_id))
    ).scalars().all()
    events.append(progress.describe_plan(
        [{"block_id": r.block_id, "action_type": r.action_type, "sequence": r.sequence,
          "recommended_at": r.recommended_at, "defer_cause": r.defer_cause} for r in recs],
        labels,
    ))
    pending = (
        await session.execute(
            select(CalendarEventProposal).where(
                CalendarEventProposal.run_id == run.run_id, CalendarEventProposal.status == "pending_approval"
            )
        )
    ).scalars().all()
    if pending:
        events.append(progress.event(
            "calendar_mcp",
            f"{len(pending)} cadangan jadual menunggu kelulusan anda.",
            f"{len(pending)} schedule proposal(s) await your approval.",
            "approval",
        ))
    for i, ev in enumerate(events):
        ev["seq"] = i
    return events


@router.get("/agent/runs/{run_id}/events")
async def agent_run_events(
    run_id: str, after: int = -1, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Live activity feed for one run: every event with seq > `after`, the
    step currently in progress, and whether the run has finished."""
    live = progress.get(run_id)
    if live is not None:
        return {
            "run_id": run_id,
            "status": live.status,
            "done": live.status != "running",
            "current": live.current,
            "events": [e for e in live.events if e["seq"] > after],
        }
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    if run.status == "running":
        # Row says running but no live feed: the process that owned it died.
        return {"run_id": run_id, "status": "failed", "done": True, "current": None, "events": []}
    events = await _rebuild_events(session, run)
    return {
        "run_id": run_id,
        "status": "done" if run.status in ("ok", "partial") else run.status,
        "done": True,
        "current": None,
        "events": [e for e in events if e["seq"] > after],
    }


@router.get("/farm/{farm_id}/advisor", response_model=AdvisorVerdictOut)
async def get_advisor(farm_id: str, session: AsyncSession = Depends(get_session)) -> AdvisorVerdictOut:
    """Computed at request time -- no background polling (pepperdex-rules skill §6)."""
    weather = get_weather(farm_id)
    rain_48h = sum(o.rainfall_mm for o in weather.rainfall_7d[:2])
    rain_since_last = sum(o.rainfall_mm for o in weather.rainfall_7d)
    verdict = await should_diagnose(session, farm_id, rain_48h_mm=rain_48h, rain_since_last_cycle_mm=rain_since_last)
    return await next_best_check(
        session, farm_id, verdict, [(f.forecast_date, f.rainfall_mm) for f in weather.forecast_7d]
    )


class ChatTurn(BaseModel):
    role: str = Field(description="'user' or 'advisor'")
    text: str = Field(max_length=2000)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    # Optional so older clients keep working; without it the Advisor has no
    # farm memory and can only answer general questions.
    farm_id: Optional[str] = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


@router.post("/advisor/ask")
async def advisor_ask(req: AskRequest, session: AsyncSession = Depends(get_session)) -> dict:
    """Free-form "Tanya" question, answered by the Advisor agent over
    retrieval. Explains why; never decides what -- the agent's only tool is
    scoped away from the authoritative namespace, so it cannot reach a dose,
    product, or timing (pepperdex-rules §2).
    """
    return await run_advisor_question(
        session, req.question.strip(), farm_id=req.farm_id,
        history=[t.model_dump() for t in req.history],
    )


@router.get("/recommendations/{recommendation_id}/blueprint")
async def recommendation_blueprint(
    recommendation_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """How this recommendation was derived, reconstructed from what was logged.

    Every step here comes from the `agent_runs.tools_called` record written
    during the run that produced this recommendation -- the same field that
    exists to evidence orchestration. **Nothing is re-inferred and nothing is
    narrated by a model**: if a tool was not called, no step appears for it.
    A blueprint that asked an LLM to explain the decision afterwards would be
    a plausible story about the decision, not the decision, and the two come
    apart precisely when it matters.

    The deferral step is the arbitration made visible: it reports the cause
    recorded on the recommendation itself, which `_reconcile_spray_deferrals`
    already overrides with the real find_spray_window result rather than
    trusting the model's account of its own reasoning.
    """
    from app.models.agent import AgentRun, Recommendation
    from app.models.core import Block

    rec = await session.get(Recommendation, recommendation_id)
    if rec is None:
        raise HTTPException(404, "recommendation not found")

    run = await session.get(AgentRun, rec.run_id) if rec.run_id else None
    block = await session.get(Block, rec.block_id) if rec.block_id else None

    # Human-readable label per tool. Unknown tools fall through to their raw
    # name rather than being hidden, so a newly added tool shows up in the
    # blueprint immediately instead of silently vanishing from the audit.
    LABELS = {
        "diagnose_leaf": ("L1 · Diagnosis", "Menilai gambar yang diambil"),
        "get_weather": ("Cuaca", "Menyemak hujan lepas dan ramalan"),
        "compute_spread": ("L2 · Sebaran", "Mengunjur laluan air ke blok hilir"),
        "get_treatment": ("L3 · Jadual rawatan", "Mengambil rawatan yang dibenarkan"),
        "find_spray_window": ("Tetingkap semburan", "Mencari masa kering yang cukup"),
        "retrieve_knowledge": ("L3 · Pengetahuan", "Mencari penerangan berkaitan"),
        "explain_why": ("Penerangan", "Menyusun sebab dalam bahasa mudah"),
        "draft_alert": ("Amaran jiran", "Menyediakan draf mesej untuk kelulusan"),
    }

    steps = []
    for call in (run.tools_called if run else []) or []:
        name = call.get("name", "?")
        label, why = LABELS.get(name, (name, ""))
        steps.append({
            "tool": name,
            "label": label,
            "what_for": why,
            "args": call.get("args", {}),
            "latency_ms": call.get("latency_ms"),
            "result_summary": (call.get("result_summary") or "")[:280],
        })

    return {
        "recommendation_id": rec.recommendation_id,
        "block_label": block.label if block else None,
        "action_type": rec.action_type,
        "sequence": rec.sequence,
        "recommended_at": rec.recommended_at.isoformat() if rec.recommended_at else None,
        "reason_ms": rec.reason_ms,
        "confidence_note": rec.confidence_note,
        # The arbitration itself: what was deferred, and on what evidence.
        "deferral": {
            "deferred_from": rec.deferred_from.isoformat() if rec.deferred_from else None,
            "defer_cause": rec.defer_cause,
        } if rec.deferred_from or rec.defer_cause else None,
        "run": {
            "run_id": run.run_id,
            "trigger": run.trigger,
            "llm_model": run.llm_model,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        } if run else None,
        "steps": steps,
        # Stated rather than implied: an empty step list means the run logged
        # no tool calls, not that the blueprint failed to load.
        "steps_note": "Setiap langkah direkod semasa keputusan dibuat, bukan dijana semula.",
    }
