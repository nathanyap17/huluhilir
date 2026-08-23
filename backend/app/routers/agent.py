from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.runner import run_advisor_question, run_root_agent
from app.db import get_session
from app.schemas.advisor import AdvisorVerdictOut
from app.schemas.agent import AgentRunOut
from app.tools.advisor import should_diagnose
from app.tools.weather import get_weather

router = APIRouter(tags=["agent"])


class AgentRunRequest(BaseModel):
    farm_id: str
    message: str
    cycle_id: Optional[str] = None
    trigger: str = "manual"


@router.post("/agent/run", response_model=AgentRunOut)
async def agent_run(req: AgentRunRequest, session: AsyncSession = Depends(get_session)) -> AgentRunOut:
    agent_run_row = await run_root_agent(
        session, req.farm_id, req.message, cycle_id=req.cycle_id, trigger=req.trigger
    )
    await session.commit()
    return AgentRunOut.model_validate(agent_run_row)


@router.get("/farm/{farm_id}/advisor", response_model=AdvisorVerdictOut)
async def get_advisor(farm_id: str, session: AsyncSession = Depends(get_session)) -> AdvisorVerdictOut:
    """Computed at request time -- no background polling (huluhilir-rules skill §6)."""
    weather = get_weather(farm_id)
    rain_48h = sum(o.rainfall_mm for o in weather.rainfall_7d[:2])
    rain_since_last = sum(o.rainfall_mm for o in weather.rainfall_7d)
    return await should_diagnose(session, farm_id, rain_48h_mm=rain_48h, rain_since_last_cycle_mm=rain_since_last)


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


@router.post("/advisor/ask")
async def advisor_ask(req: AskRequest, session: AsyncSession = Depends(get_session)) -> dict:
    """Free-form "Tanya" question, answered by the Advisor agent over
    retrieval. Explains why; never decides what -- the agent's only tool is
    scoped away from the authoritative namespace, so it cannot reach a dose,
    product, or timing (huluhilir-rules §2).
    """
    return await run_advisor_question(session, req.question.strip())


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
