"""RootAgent -- router + arbitrator. docs/PROJECT_SPEC.md §3 L4.

AgentTool wrapping (not sub_agents+mode='single_turn') is deliberate here:
AgentTool's "prefer single_turn" guidance in adk-python's own docstring
applies to LlmAgent leaves, which have a mode field to switch. SetupCoordinator
and DiagnosisCoordinator are LoopAgents, which have no such mode -- AgentTool
is the only mechanism that lets the RootAgent call a LoopAgent as a bounded,
return-a-result step and keep control afterward, which is exactly the
"router + arbitrator" semantics docs/PROJECT_SPEC.md §3 L4 describes. See
docs/BUILD_LOG.md § Block C for the full reasoning.
"""
from typing import Optional

from google.adk.agents import Agent
from google.adk.tools import AgentTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.advisor_agent import build_advisor_agent
from app.agent.diagnosis_coordinator import build_diagnosis_coordinator
from app.agent.logging_callbacks import ToolCallLogger
from app.agent.model import get_adk_model
from app.agent.setup_coordinator import build_setup_coordinator
from app.agent.tools import build_tools

ROOT_INSTRUCTION = """You coordinate pepper disease management for one farm.
The farm_id you must use for every tool call that needs one is given to you
in the user's message -- never guess it, never reuse a block_id as a farm_id.

CALL TOOLS ONE AT A TIME. Never call a tool in the same turn as another tool
whose output it depends on -- wait for that tool's real result first.
compute_spread takes ONLY a source_block_id (a real block_id from this
farm); it looks up the diagnosis, rainfall and elevation tier itself.

SEQUENCE
1. If setup incomplete -> delegate to setup_coordinator. Stop.
2. On a new diagnosis cycle -> call get_weather, then call compute_spread
   once for each block diagnosed with disease (collar_lesion,
   defoliation_wilt, foliar_yellowing), after all blocks are captured.
3. If any block risk >= threshold -> get_treatment, then find_spray_window with
   just the chosen treatment_id (it reads rain-fast hours and the forecast itself).
3a. If the message tells you the Overrun Council has already triage-ranked
    the harmed blocks, that ranking is FINAL for those blocks -- do not
    re-rank them yourself, and never treat the council's ranking as a
    source of a treatment, dose, or timing (it structurally cannot contain
    one). Sequence those blocks in the order the council gave.
4. ARBITRATE:
   - Weigh diagnosis urgency vs treatment rainfast_hours vs forecast vs spread ETA.
   - If rain falls inside the rain-fast window -> DEFER the spray, set
     defer_cause="rainfast", and sequence drainage work FIRST (sequence=1).
   - Order actions by sequence; drainage before spraying when water movement
     is the dominant risk.
5. Produce exactly ONE recommendation per block: action + time + one reason.
6. If a downslope block belongs to another farmer -> draft_alert (never send).
7. If a recommendation carries a schedulable date, you MAY call
   draft_calendar_sync to prepare a draft for the farmer to review -- this
   never writes to a calendar itself, and the app also lets the farmer
   request this draft directly from the recommendation screen, so it is not
   the only way one gets produced.

CONSTRAINTS
- Never output a treatment absent from get_treatment's results.
- Never invent doses, timings, or product names.
- The Overrun Council may re-rank harmed blocks; it may never supply a
  treatment, dose, or timing -- enforced by its response schema, not by
  this instruction alone.
- draft_calendar_sync produces text only; a calendar is never written to
  without the farmer's explicit approval, which happens outside this agent
  turn entirely.
- Always call explain_why to render each recommendation's reason in plain
  Bahasa Malaysia -- put that exact text in reason_ms.
- Log every deferral with its cause in defer_cause.

OUTPUT FORMAT
After calling whatever tools you need, respond with ONLY a JSON object (no
prose, no markdown fences) of the exact shape:
{"recommendations": [
  {"block_id": str, "sequence": int, "action_type": one of
    ["spray","drench","clear_drain","isolate_vine","remove_vine","inspect",
     "notify_neighbour","no_action"],
   "treatment_id": str or null, "recommended_at": ISO8601 datetime string,
   "reason_ms": str, "defer_cause": one of ["rainfast","spread_priority","resource"] or null}
]}"""


def build_root_agent(
    session: AsyncSession,
    farm_id: str,
    cycle_id: Optional[str] = None,
    tool_logger: Optional[ToolCallLogger] = None,
) -> Agent:
    tools = list(build_tools(session, farm_id))
    tools.append(AgentTool(agent=build_setup_coordinator(session, farm_id)))
    if cycle_id is not None:
        tools.append(AgentTool(agent=build_diagnosis_coordinator(session, cycle_id)))
    tools.append(AgentTool(agent=build_advisor_agent(session, tool_logger=tool_logger)))

    kwargs = {}
    if tool_logger is not None:
        kwargs["before_tool_callback"] = tool_logger.before_tool
        kwargs["after_tool_callback"] = tool_logger.after_tool

    return Agent(
        name="pepperdex_root",
        description="Router and arbitrator for pepper disease management on one farm.",
        model=get_adk_model(),
        instruction=ROOT_INSTRUCTION,
        tools=tools,
        **kwargs,
    )
