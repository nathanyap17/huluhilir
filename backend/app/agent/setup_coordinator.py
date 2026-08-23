"""SetupCoordinator -- LoopAgent, max_iterations=25 (docs/PROJECT_SPEC.md §5).

google-adk skill §2: loop termination checks are deterministic Python, never
LLM judgement -- SetupStateChecker queries the DB directly. The LLM
(SetupPrompter) only ever picks which speech_template_id to speak next; it
never decides whether setup is complete.

Known limitation (see docs/BUILD_LOG.md § Block C): the actual block-capture
loop described in docs/PROJECT_SPEC.md §5 happens on the phone, which doesn't
exist until Block D (Flutter). Until then this coordinator can only ever
observe "already complete" (farms.setup_completed_at is set) or "incomplete"
against whatever a test seeds -- there's no live capture step behind it to
drive it to completion. It exists now, structurally correct and bounded, so
Block D only needs to wire up the phone-side prompts.
"""
from typing import AsyncGenerator

from google.adk.agents import Agent, BaseAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.model import get_adk_model
from app.models.core import Farm

SETUP_PROMPTER_INSTRUCTION = """Setup is not yet complete for this farm.
Pick the single most relevant setup speech_template_id to speak next, from:
setup_walk_start, setup_block_capture_prompt, setup_more_blocks,
setup_elevation_pair_question, setup_drainage_prompt, setup_neighbour_prompt.
Respond with ONLY the template_id, nothing else -- no punctuation, no prose."""


class SetupStateChecker(BaseAgent):
    """Deterministic: is this farm's setup already complete? Escalates
    (stops the loop) as soon as farms.setup_completed_at is set."""

    session: AsyncSession
    farm_id: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        farm = await self.session.get(Farm, self.farm_id)
        is_complete = farm is not None and farm.setup_completed_at is not None
        yield Event(author=self.name, actions=EventActions(escalate=is_complete))


def build_setup_coordinator(session: AsyncSession, farm_id: str) -> LoopAgent:
    checker = SetupStateChecker(name="setup_state_checker", session=session, farm_id=farm_id)
    prompter = Agent(name="setup_prompter", model=get_adk_model(), instruction=SETUP_PROMPTER_INSTRUCTION)
    return LoopAgent(
        name="setup_coordinator",
        description="Walks a farmer through block capture and elevation resolution until setup is complete.",
        sub_agents=[checker, prompter],
        max_iterations=25,
    )
