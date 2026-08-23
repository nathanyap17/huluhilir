"""Advisor -- LlmAgent + RAG, non-loop (docs/PROJECT_SPEC.md §3 L4).

Two distinct things share the name "Advisor" in the spec:
1. should_diagnose() (app/tools/advisor.py) -- the deterministic "when should
   I diagnose" verdict, computed at request time, never through the LLM.
2. This agent -- answers free-form "Tanya" questions ("why not yet?", "what
   causes foot rot?") using retrieval over knowledge_docs. It explains; it
   never decides a dose/product/timing (huluhilir-rules skill §1) because its
   only tool is retrieve_knowledge, which is hard-scoped away from the
   authoritative namespace.
"""
from typing import Optional

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.logging_callbacks import ToolCallLogger
from app.agent.model import get_adk_model
from app.schemas.knowledge import RetrievalHit, RetrievalQuery
from app.tools.knowledge import retrieve_knowledge as retrieve_knowledge_impl

ADVISOR_INSTRUCTION = """You answer a pepper farmer's questions about disease management in plain
Bahasa Malaysia, using ONLY facts returned by retrieve_knowledge.

- Always call retrieve_knowledge first for any factual question.
- If retrieval returns nothing relevant, say you don't have that information --
  never guess or fabricate an answer.
- NEVER state a dose, product name, or treatment timing yourself, even if asked
  directly -- say the farmer should check the app's treatment recommendation
  instead. Only the rules table (via get_treatment, not available to you) may
  supply those.
- Keep answers short: 1-3 sentences."""


def build_advisor_agent(session: AsyncSession, tool_logger: Optional[ToolCallLogger] = None) -> Agent:
    async def retrieve_knowledge(query: str, top_k: int = 5) -> list[RetrievalHit]:
        """Search the advisory knowledge base for chunks relevant to a
        farmer's question. Returns namespace='advisory' or 'local' content
        only -- never a dose, product, or timing."""
        req = RetrievalQuery(query=query, namespaces=["advisory", "local"], top_k=top_k)
        return await retrieve_knowledge_impl(session, req)

    kwargs = {}
    if tool_logger is not None:
        kwargs["before_tool_callback"] = tool_logger.before_tool
        kwargs["after_tool_callback"] = tool_logger.after_tool

    return Agent(
        name="advisor",
        description="Answers farmer questions about disease management using retrieval over advisory knowledge docs.",
        model=get_adk_model(),
        instruction=ADVISOR_INSTRUCTION,
        tools=[FunctionTool(func=retrieve_knowledge)],
        **kwargs,
    )
