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
whose output it depends on -- wait for that tool's real result first. In
particular: NEVER call compute_spread until you have already seen
get_weather's actual response; never pass a placeholder, guessed, or
made-up number (e.g. -9999) for rainfall_7d_mm/forecast_7d_mm -- use the
real values get_weather returned.

SEQUENCE
1. If setup incomplete -> delegate to setup_coordinator. Stop.
2. On a new diagnosis cycle -> call get_weather and wait for its result, then
   call compute_spread ONCE with those real numbers, after all blocks are
   captured (not per block -- partial projection causes flapping).
3. If any block risk >= threshold -> get_treatment, then find_spray_window.
4. ARBITRATE:
   - Weigh diagnosis urgency vs treatment rainfast_hours vs forecast vs spread ETA.
   - If rain falls inside the rain-fast window -> DEFER the spray, set
     defer_cause="rainfast", and sequence drainage work FIRST (sequence=1).
   - Order actions by sequence; drainage before spraying when water movement
     is the dominant risk.
5. Produce exactly ONE recommendation per block: action + time + one reason.
6. If a downslope block belongs to another farmer -> draft_alert (never send).

CONSTRAINTS
- Never output a treatment absent from get_treatment's results.
- Never invent doses, timings, or product names.
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
        name="huluhilir_root",
        description="Router and arbitrator for pepper disease management on one farm.",
        model=get_adk_model(),
        instruction=ROOT_INSTRUCTION,
        tools=tools,
        **kwargs,
    )
