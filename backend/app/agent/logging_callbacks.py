"""tools_called logging -- never cut, it's the demo evidence of visible
orchestration (docs/PROJECT_SPEC.md §3 L4 / docs/DATA_MODEL.md §15).

Wired as before_tool_callback/after_tool_callback on the RootAgent so every
tool call (deterministic or LLM-backed, top-level or inside a sub-agent
invoked via AgentTool) gets recorded with {name, args, latency_ms,
result_summary}, independent of whether the model's final text happens to
mention it.
"""
import time
from collections import defaultdict
from typing import Any


class ToolCallLogger:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._starts: dict[str, list[float]] = defaultdict(list)

    def before_tool(self, tool, args: dict, tool_context) -> None:
        self._starts[tool.name].append(time.perf_counter())

    def after_tool(self, tool, args: dict, tool_context, tool_response: Any) -> None:
        starts = self._starts[tool.name]
        started_at = starts.pop() if starts else time.perf_counter()
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        self.calls.append({
            "name": tool.name,
            "args": _jsonable(args),
            "latency_ms": latency_ms,
            "result_summary": _summarize(tool_response),
            # Full response, kept only for in-process deterministic
            # reconciliation (app/agent/runner.py) -- stripped before this
            # list is persisted as agent_runs.tools_called, which must match
            # docs/DATA_MODEL.md §15's {name, args, latency_ms,
            # result_summary} shape exactly.
            "_raw_result": _jsonable(tool_response),
        })

    def public_calls(self) -> list[dict[str, Any]]:
        """The DB-persistable view of self.calls -- drops _raw_result."""
        return [{k: v for k, v in c.items() if k != "_raw_result"} for c in self.calls]


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _summarize(response: Any, max_len: int = 200) -> str:
    text = str(_jsonable(response))
    return text if len(text) <= max_len else text[: max_len - 3] + "..."
