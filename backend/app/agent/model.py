"""Model construction for both ADK agents and the raw LLM-backed tools.

Switching LOCAL <-> CLOUD is configuration only (LITELLM_MODEL env var) --
pepperdex-rules skill §11. Nothing here branches on deployment target.
"""
import os

from google.adk.models.lite_llm import LiteLlm

from app.config import settings


def get_adk_model() -> LiteLlm:
    kwargs = {}
    if settings.litellm_model.startswith("ollama_chat/"):
        kwargs["api_base"] = settings.ollama_api_base
    if settings.litellm_model.startswith("vertex_ai/") and settings.vertexai_project:
        # litellm reads these directly from the environment, not from kwargs
        # passed to LiteLlm() -- see LiteLlm's own docstring.
        os.environ["VERTEXAI_PROJECT"] = settings.vertexai_project
        os.environ["VERTEXAI_LOCATION"] = settings.vertexai_location
    return LiteLlm(model=settings.litellm_model, **kwargs)


async def complete_text(prompt: str, system: str | None = None) -> str:
    """Raw one-shot LiteLLM call for the LLM-backed tools (explain_why,
    draft_alert) -- these are tools, not agents: one prompt in, text out, no
    tool-calling loop of their own (pepperdex-rules skill §4 / google-adk
    skill § "Sub-agent vs LLM-backed tool").
    """
    import litellm

    kwargs = {}
    if settings.litellm_model.startswith("ollama_chat/"):
        kwargs["api_base"] = settings.ollama_api_base
    if settings.litellm_model.startswith("vertex_ai/") and settings.vertexai_project:
        os.environ["VERTEXAI_PROJECT"] = settings.vertexai_project
        os.environ["VERTEXAI_LOCATION"] = settings.vertexai_location

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = await litellm.acompletion(model=settings.litellm_model, messages=messages, **kwargs)
    return response.choices[0].message.content.strip()
