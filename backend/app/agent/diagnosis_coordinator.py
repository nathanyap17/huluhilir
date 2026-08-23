"""DiagnosisCoordinator -- LoopAgent, max_iterations=30 (docs/PROJECT_SPEC.md §6).

Same deterministic-checker principle as SetupCoordinator. CaptureChecker
reads diagnosis_cycles.blocks_captured/blocks_total directly rather than
re-deriving per-block state -- a coarser check than PROJECT_SPEC's full
per-block CaptureChecker, but correct as far as it goes and upgradeable
without touching the loop's bounding logic. See docs/BUILD_LOG.md § Block C
for why ClassifyStep/ProjectStep/TreatmentStep/ArbitrateStep aren't separate
sub-agents here yet -- the RootAgent's own tool-calling loop does that work
directly today (diagnose_leaf, compute_spread, get_treatment,
find_spray_window are all RootAgent tools); this coordinator's job for now is
strictly "is capture done, and if not, what do we say next."
"""
from typing import AsyncGenerator

from google.adk.agents import Agent, BaseAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.model import get_adk_model
from app.models.diagnosis import DiagnosisCycle

CAPTURE_PROMPTER_INSTRUCTION = """Not every block has a photo yet this diagnosis cycle.
Pick the single most relevant speech_template_id to prompt the farmer for the
next capture: diagnosis_capture_next, diagnosis_retake_wrong_target, or
diagnosis_retake_unrelated. Respond with ONLY the template_id, nothing else."""


class CaptureChecker(BaseAgent):
    """Deterministic: are all blocks captured for this diagnosis cycle?
    Escalates as soon as diagnosis_cycles.blocks_captured >= blocks_total."""

    session: AsyncSession
    cycle_id: str

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        cycle = await self.session.get(DiagnosisCycle, self.cycle_id)
        is_complete = cycle is not None and cycle.blocks_captured >= cycle.blocks_total
        yield Event(author=self.name, actions=EventActions(escalate=is_complete))


def build_diagnosis_coordinator(session: AsyncSession, cycle_id: str) -> LoopAgent:
    checker = CaptureChecker(name="capture_checker", session=session, cycle_id=cycle_id)
    prompter = Agent(name="capture_prompter", model=get_adk_model(), instruction=CAPTURE_PROMPTER_INSTRUCTION)
    return LoopAgent(
        name="diagnosis_coordinator",
        description="Walks a farmer through photographing every block in one diagnosis cycle until capture is complete.",
        sub_agents=[checker, prompter],
        max_iterations=30,
    )
