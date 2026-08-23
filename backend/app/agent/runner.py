"""Runs the RootAgent for one turn and persists the result.

This is the seam between ADK and the rest of the app: builds a fresh
RootAgent scoped to one DB session/farm, drives it with google.genai
Content, parses its final JSON recommendations, and writes agent_runs +
recommendations rows -- including tools_called, which must never be
dropped (docs/DATA_MODEL.md §15).
"""
import json
import re
from datetime import datetime
from typing import Optional

from google.adk.runners import InMemoryRunner
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.logging_callbacks import ToolCallLogger
from app.agent.root_agent import build_root_agent
from app.config import settings
from app.models.agent import AgentRun, Recommendation
from app.models.base import now_kuching

APP_NAME = "huluhilir"

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """The model is instructed to emit ONLY JSON, but small local models
    occasionally wrap it in prose or a markdown fence anyway -- salvage the
    first {...} block rather than failing the whole run on that."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))


_RAINFAST_GATED_ACTIONS = {"spray", "drench"}


def _reconcile_spray_deferrals(recommendations_data: list[dict], calls: list[dict]) -> list[dict]:
    """Deterministic safety net over the LLM's arbitration, not a replacement
    for it (google-adk skill: loop/termination logic is deterministic Python,
    never LLM judgement -- extended here to the rainfast defer decision
    specifically, because empirical testing showed qwen2.5:14b unreliably
    incorporates find_spray_window's defer_cause into its final JSON even
    when explicitly instructed to (see docs/BUILD_LOG.md § Block C for the
    observed failure: 5 identical "treat now" recommendations with
    defer_cause=null despite find_spray_window returning rain_free=False for
    every near-term window). This function overrides defer_cause and
    recommended_at for rainfast-gated actions using find_spray_window's
    ACTUAL last-called result, and injects a clear_drain recommendation
    ahead of any deferred spray if the model didn't already produce one --
    "drainage before spraying when water movement is the dominant risk"
    (docs/PROJECT_SPEC.md §3 L4) enforced structurally, not hoped for.
    """
    spray_calls = [c for c in calls if c["name"] == "find_spray_window"]
    if not spray_calls:
        return recommendations_data

    raw = spray_calls[-1].get("_raw_result") or {}
    result = raw.get("result", raw) if isinstance(raw, dict) else {}
    if not isinstance(result, dict) or "defer_cause" not in result:
        return recommendations_data

    actual_defer_cause = result.get("defer_cause")
    recommended_window = result.get("recommended_window")

    reconciled = []
    needs_drainage_first = False
    for rec in recommendations_data:
        rec = dict(rec)
        if rec.get("action_type") in _RAINFAST_GATED_ACTIONS and rec.get("treatment_id"):
            rec["defer_cause"] = actual_defer_cause
            # The real computed window always wins over anything the model
            # wrote for recommended_at -- observed failure mode was the model
            # fabricating an unrelated date (e.g. "2023-10-06") even when
            # defer_cause was correctly None and a real window existed.
            if recommended_window and recommended_window.get("window_start"):
                rec["recommended_at"] = recommended_window["window_start"]
            if actual_defer_cause == "rainfast":
                needs_drainage_first = True
        reconciled.append(rec)

    if needs_drainage_first and not any(r.get("action_type") == "clear_drain" for r in reconciled):
        first_block_id = reconciled[0]["block_id"] if reconciled else None
        if first_block_id:
            for r in reconciled:
                r["sequence"] = r.get("sequence", 1) + 1
            reconciled.insert(0, {
                "block_id": first_block_id,
                "sequence": 1,
                "action_type": "clear_drain",
                "treatment_id": None,
                "recommended_at": now_kuching().isoformat(),
                "reason_ms": "Buka parit sekarang -- hujan dijangka dalam tempoh tahan hujan racun.",
                "defer_cause": None,
            })

    return reconciled


async def run_root_agent(
    session: AsyncSession,
    farm_id: str,
    user_message: str,
    cycle_id: Optional[str] = None,
    trigger: str = "manual",
) -> AgentRun:
    """Runs one RootAgent turn and persists agent_runs + recommendations.
    Caller is responsible for session.commit()."""
    tool_logger = ToolCallLogger()
    root_agent = build_root_agent(session, farm_id, cycle_id=cycle_id, tool_logger=tool_logger)

    adk_runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    user_id, session_id = f"farm_{farm_id}", f"run_{farm_id}"
    await adk_runner.session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

    started_at = now_kuching()
    final_text = ""
    async for event in adk_runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=user_message)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    status = "ok"
    recommendations_data = []
    try:
        parsed = _extract_json(final_text)
        recommendations_data = parsed.get("recommendations", [])
    except (json.JSONDecodeError, AttributeError):
        status = "partial"

    recommendations_data = _reconcile_spray_deferrals(recommendations_data, tool_logger.calls)

    agent_run = AgentRun(
        farm_id=farm_id,
        trigger=trigger,
        cycle_id=cycle_id,
        tools_called=tool_logger.public_calls(),
        llm_model=settings.litellm_model,
        started_at=started_at,
        completed_at=now_kuching(),
        status=status,
    )
    session.add(agent_run)
    await session.flush()

    for rec in recommendations_data:
        session.add(Recommendation(
            run_id=agent_run.run_id,
            block_id=rec["block_id"],
            sequence=rec.get("sequence", 1),
            action_type=rec["action_type"],
            treatment_id=rec.get("treatment_id"),
            recommended_at=datetime.fromisoformat(rec["recommended_at"]),
            reason_ms=rec.get("reason_ms", ""),
            defer_cause=rec.get("defer_cause"),
        ))

    return agent_run
