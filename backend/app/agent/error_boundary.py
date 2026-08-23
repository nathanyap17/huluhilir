"""Wraps an ADK tool function so any exception becomes a retryable
{"error": ...} response instead of crashing the whole agent run.

Needed because ADK's function-calling flow lets an unhandled exception from
inside a tool propagate all the way up through asyncio.gather and kill the
entire turn -- observed when a local model called compute_spread in parallel
with get_weather, before get_weather's result was available, using a
placeholder like -9999 for the still-unknown rainfall figures. Pydantic's
validation correctly rejected that, but with no boundary here the whole
agent run died instead of the model getting a chance to retry with real
numbers. See docs/BUILD_LOG.md § Block C.

Uses functools.wraps so inspect.signature() (which ADK's schema builder
calls on tool.func) still resolves through to the wrapped function's real
signature and docstring -- the LLM-facing tool declaration is unaffected.
"""
import functools
import inspect
from typing import Any, Callable


def tool_error_boundary(func: Callable[..., Any]) -> Callable[..., Any]:
    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return {"error": f"{type(e).__name__}: {e}. Check your arguments and retry with real values."}
        return async_wrapper

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}. Check your arguments and retry with real values."}
    return sync_wrapper
