---
name: google-adk
description: Reference for building agents with Google ADK (Agent Development Kit) in Python. Use whenever writing or modifying agent code — LlmAgent, LoopAgent, SequentialAgent, FunctionTool, AgentTool, sub_agents, session state, callbacks, or LiteLLM model integration. Also use when debugging agent loops that don't terminate, tool schemas the LLM ignores, or model configuration errors.
---

# Google ADK Reference

## Local source of truth

Two repositories are cloned at the workspace root. **Read from them rather than relying on memory** — ADK's API changes between versions.

```
../adk-docs/      # official documentation (markdown)
../adk-python/    # source code — authoritative on actual signatures
```

**Lookup order:**
1. `../adk-docs/docs/agents/` — conceptual guides
2. `../adk-python/src/google/adk/agents/` — real class signatures
3. `../adk-python/src/google/adk/tools/` — tool implementations
4. Only then, general knowledge

**When unsure of a signature, grep the source:**
```bash
grep -rn "class LoopAgent" ../adk-python/src/
grep -rn "max_iterations" ../adk-python/src/
grep -rn "escalate" ../adk-python/src/
```

---

## Agent types used in this project

| Type | Use | PepperDex usage |
|---|---|---|
| `LlmAgent` | Reasoning, routing, tool selection | `RootAgent`, `Advisor` |
| `LoopAgent` | Repeat sub-agents until escalation | `SetupCoordinator`, `DiagnosisCoordinator` |
| `SequentialAgent` | Fixed ordered pipeline | Not used |
| `ParallelAgent` | Concurrent fan-out | Not used |

---

## Critical patterns

### 1 · LoopAgent must always bound iterations

```python
from google.adk.agents import LoopAgent

setup_coordinator = LoopAgent(
    name="setup_coordinator",
    sub_agents=[setup_step_checker, setup_prompter],
    max_iterations=25,          # NEVER omit — unbounded loops kill the demo
)
```

Termination happens when a sub-agent calls `escalate()` **or** `max_iterations` is reached. Always provide both paths.

### 2 · Loop termination checks are deterministic Python, not LLM judgement

The checker queries the database and returns structured state. The LLM's only job is choosing which `template_id` to speak.

```python
def check_setup_state(farm_id: str) -> SetupState:
    """Deterministic. Returns is_complete and next_action."""
    ...
```

**Never** let an LLM decide whether setup or a diagnosis cycle is complete — it will occasionally get it wrong in a way that cannot be debugged live.

### 3 · Tools are Pydantic-typed

Define I/O once; the schema feeds FastAPI, the ADK tool spec, and generated Dart models.

```python
from google.adk.tools import FunctionTool

def compute_spread(req: SpreadRequest) -> SpreadResponse:
    """Project downhill disease spread across the farm's elevation graph.

    Returns per-block risk score, band, and estimated arrival in days.
    Always an estimate — is_estimate is always True.
    """
    ...

spread_tool = FunctionTool(func=compute_spread)
```

**Docstrings are the LLM's tool description.** Write them for the model: what it does, when to call it, what it returns.

### 4 · Sub-agent vs LLM-backed tool — do not conflate

| | LLM-backed `FunctionTool` | Sub-agent (`AgentTool` / `sub_agents`) |
|---|---|---|
| Autonomy | None — one prompt in, text out | Own instruction, own tools, own loop |
| Control flow | Returns immediately | May iterate before returning |
| Examples here | `explain_why`, `draft_alert` | `SetupCoordinator`, `DiagnosisCoordinator`, `Advisor` |

`explain_why` and `draft_alert` are **tools**, not agents. Do not describe them as multi-agent.

### 5 · LiteLLM for local Ollama

```python
from google.adk.models.lite_llm import LiteLlm

model = LiteLlm(model="ollama_chat/gemma2:9b")
```

Provider switching is one line — configure Ollama (primary) and a cloud API (backup); test both before demo day.

### 6 · Always log tool calls

`tools_called` is demo evidence of orchestration. Persist `{name, args, latency_ms, result_summary}` to `agent_runs`. Never optimise this away.

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| Loop never ends | No `escalate()` and no `max_iterations` | Set both |
| LLM ignores a tool | Vague docstring | Rewrite for the model |
| Tool args mismatched | Hand-written schema drifted from Pydantic | Generate from `.model_json_schema()` |
| Small model won't call tools | Model too weak for function calling | See `../sandbox/EXPERIMENTS.md` EXP-5 |
| State lost between iterations | Not using session state | Read `../adk-docs/docs/sessions/` |

---

## Before writing agent code

1. `grep` the actual signature in `../adk-python/src/`
2. Check `../adk-docs/` for the current recommended pattern
3. Confirm the tool's Pydantic model exists in `backend/schemas.py`
4. Confirm `max_iterations` is set on any loop
