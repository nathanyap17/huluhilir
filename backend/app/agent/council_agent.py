"""OverrunCouncil -- ADK-native sub_agents, NOT the A2A protocol.
docs/PROJECT_SPEC.md §3 L4.

Fires only when farm_state == 'overrun' (more than one block simultaneously
`harmed`, app/tools/council.py:is_farm_overrun) -- not part of a normal
diagnosis cycle. Three specialist LlmAgents each argue in turn
(AgronomicUrgencyAgent, CostFeasibilityAgent, LogisticsAgent), then
CouncilOrchestrator reads all three arguments and ranks -- never invents a
treatment, dose, or timing. That wall is structural: TriageRanking
(app/schemas/council.py) has no field that could hold one, and
`extra="forbid"` makes an attempt to smuggle one raise instead of being
silently dropped.

Implementation note on AgentTool vs a direct runner: the architecture
diagram lists this as "AgentTool -> OverrunCouncil", same as
SetupCoordinator/DiagnosisCoordinator/Advisor. This module instead exposes
`run_overrun_council()`, driven by its own InMemoryRunner -- the same
pattern `run_advisor_question()` in app/agent/runner.py already uses for
Advisor's standalone /advisor/ask path. The reason: AgentTool's wrapper
(google/adk/tools/agent_tool.py) only returns the WRAPPED agent's merged
final text to the caller -- it does not expose the nested run's session
state afterward. Since "every debate is logged to council_debates -- the
transcript is demo evidence, not just an internal record" is a real
requirement here (not just documentation), this needs the real specialist
arguments back, not just the orchestrator's closing text. Running our own
InMemoryRunner gives direct access to session.state after the run
completes, so `council_debates.transcript` holds each specialist's ACTUAL
output, not a hopeful echo of it. The council is still, substantively, ADK-
native sub_agents (a SequentialAgent of four LlmAgents) -- not the A2A
protocol -- which is the actual claim being made, independent of which ADK
call shape reaches it from the RootAgent's tool list.
"""
import json
import re

from google.adk.agents import Agent, SequentialAgent
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.model import get_adk_model
from app.models.agent import CouncilDebate
from app.models.core import Block
from app.schemas.council import TriageRanking
from app.tools.council import fallback_ranking

_JSON_ARRAY_RE = re.compile(r"\[.*\]", re.DOTALL)


def _extract_json_array(text: str) -> list:
    """Same salvage strategy as app/agent/runner.py's _extract_json, but for
    a bare JSON array response rather than an object -- small local models
    occasionally wrap it in prose or a markdown fence anyway."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_ARRAY_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))

APP_NAME = "pepperdex_council"

_SPECIALIST_SYSTEM_PREAMBLE = """You are one of three specialists advising on which pepper farm block to
treat FIRST when several blocks are simultaneously in a harmed (collar lesion / defoliation-wilt) state.
Argue from YOUR perspective only, in 2-3 sentences of plain Bahasa Malaysia. Do NOT rank the blocks
yourself, do NOT propose a treatment, dose, or timing -- another agent decides the order afterward,
and only the rules table may ever supply a treatment. Just give your argument."""

AGRONOMIC_URGENCY_INSTRUCTION = f"""{_SPECIALIST_SYSTEM_PREAMBLE}
Your perspective: AGRONOMIC URGENCY. Which block is at the most immediate biological risk of losing the
vine, based on its state and position in the farm's water-flow order (a lower elevation_rank number is
higher upslope; disease already flows downhill from there)?"""

COST_FEASIBILITY_INSTRUCTION = f"""{_SPECIALIST_SYSTEM_PREAMBLE}
Your perspective: COST / FEASIBILITY. Which block, if treated first, protects the most vines or area for
the least likely effort, based on vine_count and drainage already given for each block?"""

LOGISTICS_INSTRUCTION = f"""{_SPECIALIST_SYSTEM_PREAMBLE}
Your perspective: LOGISTICS. Given the blocks' relative positions (elevation_rank order), which treatment
sequence minimises backtracking for a farmer walking the farm in one pass?"""

ORCHESTRATOR_INSTRUCTION = """You are the Council Orchestrator. Three specialists have each given their
argument on which harmed block to treat first:

AGRONOMIC URGENCY specialist said: {urgency_argument}

COST/FEASIBILITY specialist said: {cost_argument}

LOGISTICS specialist said: {logistics_argument}

Weigh all three and produce a final priority ranking of the harmed blocks listed in the original message.
You may only RE-ORDER the blocks already given to you -- never invent a new block_id, never mention a
treatment, dose, product name, or timing anywhere in your output; another part of the system handles
those separately and your output has no field for them.

Respond with ONLY a JSON array (no prose, no markdown fences) of the exact shape:
[{"block_id": str, "rank": int (1 = treat first), "rationale_ms": str (max 300 chars, plain Bahasa Malaysia)}]
One entry per block listed in the original message, ranks 1..N with no gaps or repeats."""


def _build_council_agent() -> SequentialAgent:
    urgency = Agent(
        name="agronomic_urgency",
        description="Argues from agronomic urgency: which block risks losing the vine soonest.",
        model=get_adk_model(),
        instruction=AGRONOMIC_URGENCY_INSTRUCTION,
        output_key="urgency_argument",
    )
    cost = Agent(
        name="cost_feasibility",
        description="Argues from cost/feasibility: which block protects the most for the least effort.",
        model=get_adk_model(),
        instruction=COST_FEASIBILITY_INSTRUCTION,
        output_key="cost_argument",
    )
    logistics = Agent(
        name="logistics",
        description="Argues from logistics: which treatment order minimises walking the farm twice.",
        model=get_adk_model(),
        instruction=LOGISTICS_INSTRUCTION,
        output_key="logistics_argument",
    )
    orchestrator = Agent(
        name="council_orchestrator",
        description="Ranks harmed blocks from the three specialists' arguments. Never generates a treatment.",
        model=get_adk_model(),
        instruction=ORCHESTRATOR_INSTRUCTION,
        output_key="ranking_json",
    )
    return SequentialAgent(
        name="overrun_council",
        description="Triage-ranks simultaneously-harmed blocks. Structurally cannot output a treatment.",
        sub_agents=[urgency, cost, logistics, orchestrator],
    )


def _block_summary_message(blocks: list[Block]) -> str:
    lines = [
        f"- block_id={b.block_id}, label={b.label!r}, elevation_rank={b.elevation_rank}, "
        f"drainage={b.drainage}, vine_count={b.vine_count if b.vine_count is not None else 'unknown'}"
        for b in blocks
    ]
    return (
        "The following blocks are all currently 'harmed' and need a triage order:\n"
        + "\n".join(lines)
    )


async def run_overrun_council(
    session: AsyncSession,
    farm_id: str,
    run_id: str,
    harmed_blocks: list[Block],
) -> list[dict]:
    """Runs the council for one set of harmed blocks, persists a
    council_debates row, and returns a validated ranking (list of
    {block_id, rank, rationale_ms} dicts).

    Falls back to app/tools/council.py's deterministic fallback_ranking()
    -- never an error -- if the orchestrator's output fails to parse or
    fails the dose-less schema wall. Either path still writes a
    council_debates row, so a fallback is visible in the demo evidence
    too, not silently swallowed.
    """
    if len(harmed_blocks) < 2:
        raise ValueError("run_overrun_council requires at least 2 harmed blocks -- this is triage, not a single decision")

    council = _build_council_agent()
    adk_runner = InMemoryRunner(agent=council, app_name=APP_NAME)
    user_id, session_id = f"farm_{farm_id}", f"council_{run_id}"
    await adk_runner.session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

    message = _block_summary_message(harmed_blocks)
    final_text = ""
    async for event in adk_runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    final_session = await adk_runner.session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    state = final_session.state if final_session else {}
    transcript = [
        {"agent": "agronomic_urgency", "argument": state.get("urgency_argument", "")},
        {"agent": "cost_feasibility", "argument": state.get("cost_argument", "")},
        {"agent": "logistics", "argument": state.get("logistics_argument", "")},
    ]

    valid_block_ids = {b.block_id for b in harmed_blocks}
    ranking: list[dict]
    try:
        items = _extract_json_array(final_text)
        validated = [TriageRanking(**item) for item in items]
        if {r.block_id for r in validated} != valid_block_ids:
            raise ValueError("orchestrator ranked a different set of blocks than it was given")
        ranking = [r.model_dump() for r in validated]
    except (json.JSONDecodeError, ValidationError, ValueError, TypeError, KeyError, AttributeError):
        ranking = fallback_ranking(harmed_blocks)

    debate = CouncilDebate(
        run_id=run_id,
        block_ids_considered=[b.block_id for b in harmed_blocks],
        transcript=transcript,
        ranked_output=ranking,
    )
    session.add(debate)

    return ranking
