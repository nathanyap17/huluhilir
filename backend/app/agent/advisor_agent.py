"""Advisor -- LlmAgent + RAG, non-loop (docs/PROJECT_SPEC.md §3 L4).

Two distinct things share the name "Advisor" in the spec:
1. should_diagnose() (app/tools/advisor.py) -- the deterministic "when should
   I diagnose" verdict, computed at request time, never through the LLM.
2. This agent -- answers free-form "Tanya" questions ("why not yet?", "what
   causes foot rot?") using retrieval over knowledge_docs. It explains; it
   never decides a dose/product/timing (pepperdex-rules skill §1) because its
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

ADVISOR_INSTRUCTION = """You are the PepperDex advisor for ONE specific black pepper (Piper nigrum) farm. The farmer grows pepper and the disease of concern is Phytophthora foot rot (collar lesion, yellowing, defoliation/wilt). Never ask what crop they grow or which disease they mean.

The message you receive starts with FARM CONTEXT: this farm's blocks, their current state, recent diagnoses, the latest action plan, projected downhill spread, rain, and calendar proposals, read from the database. It may also contain CONVERSATION SO FAR.

- Questions about THIS farm ("are my blocks safer now?", "why is Block 2 harmed?", "what should I do next?", "when is the drench?") -> answer from FARM CONTEXT. Name the blocks, compare the newest diagnosis with the previous one, quote dates. Say plainly when something got better, worse, or is unchanged.
- General knowledge questions (how foot rot spreads, why drainage matters) -> call retrieve_knowledge and answer from what it returns. You may combine both.
- Resolve follow-ups ("this", "that", "it") using CONVERSATION SO FAR.
- Spread risks are estimates, not measurements -- say so when you quote one.
- If neither FARM CONTEXT nor retrieve_knowledge contains the answer, say you don't have that information -- never guess.
- Always answer in the language the user is speaking, regardless of the language of the retrieved documents.
- You may REPEAT the action plan in FARM CONTEXT (which action, which block, which date) -- it came from the rules table. Never invent, change or re-time an action, and never state a dose or product name: point the farmer to the Priority action card for those.
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
