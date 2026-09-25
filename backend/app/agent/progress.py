"""Live, farmer-readable activity feed for one agent run.

The Advisor chat renders these as messages from named agents
(DiagnosisCoordinator, Spread model, Rules table, Overrun Council members,
Calendar MCP, RootAgent) so the minutes a local model spends arbitrating are
visible work instead of a spinner.

Every event is derived from something that actually happened -- a tool call
the ToolCallLogger captured, a council transcript row, the runner's own
fallback/guard decisions. Nothing here asks a model to narrate its reasoning
after the fact (same principle as the /blueprint endpoint).

Storage is in-process memory, keyed by run_id: enough for the local laptop
backend and a single Cloud Run instance. A finished run's feed can always be
rebuilt from agent_runs.tools_called + recommendations + council_debates
(see routers/agent.py), so losing this dict only loses the *live* view.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

ACTION_LABEL = {
    "spray": ("Sembur", "Spray"),
    "drench": ("Siram pangkal", "Drench"),
    "clear_drain": ("Bersihkan parit", "Clear drain"),
    "isolate_vine": ("Asingkan pokok", "Isolate vine"),
    "remove_vine": ("Buang pokok", "Remove vine"),
    "inspect": ("Periksa", "Inspect"),
    "notify_neighbour": ("Maklumkan jiran", "Notify neighbour"),
    "no_action": ("Tiada tindakan", "No action"),
}

CLASS_LABEL = {
    "healthy_leaf": ("daun sihat", "healthy leaf"),
    "healthy_collar": ("pangkal sihat", "healthy collar"),
    "foliar_yellowing": ("daun menguning", "foliar yellowing"),
    "collar_lesion": ("luka pangkal", "collar lesion"),
    "defoliation_wilt": ("gugur daun / layu", "defoliation / wilt"),
    "unrelated": ("gambar tidak berkaitan", "unrelated photo"),
    "unknown": ("tidak pasti", "uncertain"),
}

COUNCIL_AGENT = {
    "agronomic_urgency": "council_agronomic",
    "cost_feasibility": "council_cost",
    "logistics": "council_logistics",
}

_TTL_S = 3600


@dataclass
class RunProgress:
    status: str = "running"  # running | done | failed
    events: list[dict[str, Any]] = field(default_factory=list)
    current: Optional[dict[str, Any]] = None
    started: float = field(default_factory=time.time)
    next_seq: int = 0


_RUNS: dict[str, RunProgress] = {}


def start(run_id: str) -> None:
    now = time.time()
    for rid in [r for r, p in _RUNS.items() if now - p.started > _TTL_S]:
        _RUNS.pop(rid, None)
    _RUNS[run_id] = RunProgress()


def get(run_id: str) -> Optional[RunProgress]:
    return _RUNS.get(run_id)


def event(agent: str, ms: str, en: str, kind: str = "step") -> dict[str, Any]:
    # Runtime-composed text: spoken through /speech/say like every other
    # agent-composed string (rule 7), hence the ad-hoc template id.
    return {"agent": agent, "kind": kind, "text_ms": ms, "text_en": en, "speech_template_id": "_adhoc"}


def emit(run_id: Optional[str], agent: str, ms: str, en: str, kind: str = "step") -> None:
    p = _RUNS.get(run_id or "")
    if p is None:
        return
    last = p.events[-1] if p.events else None
    if last and last["agent"] == agent and last["text_en"] == en:
        return  # the model often repeats a read-only tool; show it once
    ev = event(agent, ms, en, kind)
    # One tool call per block (2026-09-24: two diseased blocks -> the feed
    # showed Spread Model / Rules Table twice each). Consecutive plain steps
    # from the same agent become ONE message: the new event carries the
    # combined text and `replaces` the previous seq, which the app removes.
    if last and kind == "step" and last["kind"] == "step" and last["agent"] == agent:
        if en in last["text_en"].split("\n"):
            return
        ev = event(agent, last["text_ms"] + "\n" + ms, last["text_en"] + "\n" + en, kind)
        ev["replaces"] = last["seq"]
        p.events.pop()
    ev["seq"] = p.next_seq
    p.next_seq += 1
    p.events.append(ev)


def set_current(run_id: Optional[str], agent: Optional[str], ms: str = "", en: str = "") -> None:
    p = _RUNS.get(run_id or "")
    if p is not None:
        p.current = None if agent is None else {"agent": agent, "text_ms": ms, "text_en": en}


def finish(run_id: Optional[str], status: str = "done") -> None:
    p = _RUNS.get(run_id or "")
    if p is not None:
        p.status = status
        p.current = None


# --- describing what actually happened ---------------------------------------

_BEFORE = {
    "get_weather": ("spread_model", "Mengambil data hujan (data.gov.my)…", "Fetching rainfall (data.gov.my)…"),
    "compute_spread": ("spread_model", "Mengira aliran penyakit ke bawah cerun…", "Computing downhill spread…"),
    "get_treatment": ("rules_table", "Menyemak jadual rawatan yang diluluskan…", "Checking the approved treatment table…"),
    "find_spray_window": ("rules_table", "Mencari tetingkap tanpa hujan…", "Looking for a rain-free window…"),
    "query_farm_history": ("advisor_rag", "Menyemak sejarah ladang…", "Reading farm history…"),
    "explain_why": ("advisor_rag", "Mencari sebab dalam pangkalan ilmu…", "Searching the knowledge base…"),
    "retrieve_knowledge": ("advisor_rag", "Mencari dalam pangkalan ilmu…", "Searching the knowledge base…"),
    "advisor": ("advisor_rag", "Penasihat (RAG) mencari penjelasan…", "Advisor (RAG) is looking up the explanation…"),
    "draft_alert": ("root_agent", "Merangka amaran jiran…", "Drafting a neighbour alert…"),
    "draft_calendar_sync": ("calendar_mcp", "Merangka jadual…", "Drafting a schedule…"),
    "check_calendar_schedule": ("calendar_mcp", "Membaca Google Calendar (MCP)…", "Reading Google Calendar (MCP)…"),
    "check_calendar_availability": ("calendar_mcp", "Menyemak slot kosong di Google Calendar (MCP)…", "Checking Google Calendar free slots (MCP)…"),
}


def describe_before(tool_name: str) -> Optional[tuple[str, str, str]]:
    return _BEFORE.get(tool_name)


def _unwrap(raw: Any) -> Any:
    if isinstance(raw, dict) and "result" in raw and len(raw) == 1:
        return raw["result"]
    return raw


def _fmt_day(value: Any) -> tuple[str, str]:
    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value), str(value)
    days_ms = ["Isn", "Sel", "Rab", "Kha", "Jum", "Sab", "Aha"]
    return f"{days_ms[dt.weekday()]} {dt:%d/%m %H:%M}", f"{dt:%a %d %b %H:%M}"


def describe_call(call: dict[str, Any], labels: dict[str, str]) -> Optional[dict[str, Any]]:
    """One tool call the ToolCallLogger recorded -> one feed event."""
    name = call.get("name", "")
    res = _unwrap(call.get("_raw_result"))
    args = call.get("args") or {}
    lab = lambda bid: labels.get(bid, "?")  # noqa: E731

    if name in ("check_calendar_schedule", "check_calendar_availability"):
        if isinstance(res, dict) and res.get("connected") is False:
            return event("calendar_mcp", "Tiada Google Calendar dipautkan pada ladang ini; jadual ikut ramalan cuaca sahaja.",
                         "No Google Calendar is linked to this farm; scheduling follows the forecast only.")
        return event("calendar_mcp", "Google Calendar disemak melalui MCP untuk elak pertindihan.",
                     "Google Calendar checked over MCP to avoid clashes.")

    if isinstance(res, dict) and "error" in res and len(res) <= 2:
        return event(
            "root_agent",
            f"Alat {name} menolak input yang salah; ejen cuba semula.",
            f"Tool {name} rejected malformed input; the agent retries.",
            kind="warning",
        )

    if name == "get_weather" and isinstance(res, dict):
        past = sum(float(o.get("rainfall_mm", 0)) for o in res.get("rainfall_7d", []))
        ahead = sum(float(o.get("rainfall_mm", 0)) for o in res.get("forecast_7d", []))
        cached = " (anggaran cache)" if res.get("is_cached_fallback") else ""
        cached_en = " (cached estimate)" if res.get("is_cached_fallback") else ""
        return event(
            "spread_model",
            f"Hujan 7 hari lalu ≈ {past:.0f} mm, 7 hari akan datang ≈ {ahead:.0f} mm{cached}.",
            f"Rain last 7 days ≈ {past:.0f} mm, next 7 days ≈ {ahead:.0f} mm{cached_en}.",
        )

    if name == "compute_spread" and isinstance(res, dict):
        src_id = res.get("source_block_id") or args.get("source_block_id", "")
        if src_id not in labels:
            return event(
                "root_agent",
                "Model memberi ID blok yang tidak wujud kepada model aliran -- keputusan itu diabaikan.",
                "The model passed a block id that doesn't exist to the spread model -- result ignored.",
                kind="warning",
            )
        src = lab(src_id)
        items = [r for r in res.get("results", []) if r.get("block_id") in labels]
        if not items:
            return event(
                "spread_model",
                f"Dari {src}: tiada blok di bawah cerun yang berisiko.",
                f"From {src}: no downhill block at risk.",
            )
        parts_ms, parts_en = [], []
        for r in items[:3]:
            eta = r.get("eta_days")
            pct = round(float(r.get("risk", 0)) * 100)
            parts_ms.append(f"{lab(r['block_id'])} {pct}%" + (f" dalam ~{eta} hari" if eta else ""))
            parts_en.append(f"{lab(r['block_id'])} {pct}%" + (f" in ~{eta} days" if eta else ""))
        return event(
            "spread_model",
            f"Aliran dari {src}: " + "; ".join(parts_ms) + " (anggaran, bukan ukuran).",
            f"Spread from {src}: " + "; ".join(parts_en) + " (estimates, not measurements).",
        )

    if name == "get_treatment" and isinstance(res, dict):
        opts = res.get("options", [])
        cls_ms, cls_en = CLASS_LABEL.get(res.get("predicted_class", ""), (res.get("predicted_class", ""),) * 2)
        if not opts:
            return event("rules_table", f"Tiada rawatan dalam jadual untuk {cls_ms}.", f"No listed treatment for {cls_en}.")
        return event(
            "rules_table",
            f"Rawatan diluluskan untuk {cls_ms}: " + ", ".join(o.get("name_ms", "") for o in opts[:3]) + ".",
            f"Approved treatments for {cls_en}: " + ", ".join(o.get("name_en", "") for o in opts[:3]) + ".",
        )

    if name == "find_spray_window" and isinstance(res, dict):
        if res.get("defer_cause") == "rainfast":
            return event(
                "rules_table",
                f"Hujan dijangka dalam {res.get('rainfast_hours')} jam tempoh tahan hujan -- semburan ditangguh.",
                f"Rain expected inside the {res.get('rainfast_hours')} h rainfast period -- spraying deferred.",
                kind="warning",
            )
        win = (res.get("recommended_window") or {}).get("window_start")
        if win:
            d_ms, d_en = _fmt_day(win)
            return event("rules_table", f"Tetingkap kering dijumpai: {d_ms}.", f"Dry window found: {d_en}.")
        return None

    if name in ("explain_why", "retrieve_knowledge", "advisor"):
        return event("advisor_rag", "Sebab disemak dalam pangkalan ilmu (RAG).", "Reasoning checked against the knowledge base (RAG).")

    if name == "query_farm_history":
        return event("advisor_rag", "Sejarah diagnosis ladang disemak.", "Farm diagnosis history checked.")

    if name in ("check_calendar_schedule", "check_calendar_availability"):
        return event("calendar_mcp", "Google Calendar disemak melalui MCP untuk elak pertindihan.",
                     "Google Calendar checked over MCP to avoid clashes.")

    if name == "deterministic_fallback":
        return event(
            "root_agent",
            "Model tempatan terlalu lambat/gagal -- keputusan dibuat terus dari jadual peraturan.",
            "Local model too slow or failed -- decision made directly from the rules table.",
            kind="warning",
        )

    if name == "rules_guard":
        return event(
            "root_agent",
            "Semakan peraturan membetulkan cadangan model: " + str(args.get("note_ms", "")),
            "Rules check corrected the model's plan: " + str(args.get("note_en", "")),
            kind="warning",
        )
    return None


def describe_plan(recs: list[dict[str, Any]], labels: dict[str, str]) -> dict[str, Any]:
    if not recs or all(r.get("action_type") == "no_action" for r in recs):
        return event("root_agent", "Keputusan: semua blok sihat -- tiada tindakan diperlukan.",
                     "Decision: all blocks healthy -- no action needed.", kind="final")
    lines_ms, lines_en = [], []
    for r in sorted(recs, key=lambda r: r.get("sequence", 1)):
        if r.get("action_type") == "no_action":
            continue
        a_ms, a_en = ACTION_LABEL.get(r["action_type"], (r["action_type"],) * 2)
        d_ms, d_en = _fmt_day(r.get("recommended_at", ""))
        defer_ms = " (ditangguh: hujan)" if r.get("defer_cause") else ""
        defer_en = " (deferred: rain)" if r.get("defer_cause") else ""
        lines_ms.append(f"{len(lines_ms) + 1}. {a_ms} -- {labels.get(r['block_id'], '?')}, {d_ms}{defer_ms}")
        lines_en.append(f"{len(lines_en) + 1}. {a_en} -- {labels.get(r['block_id'], '?')}, {d_en}{defer_en}")
    return event("root_agent", "Keputusan:\n" + "\n".join(lines_ms), "Decision:\n" + "\n".join(lines_en), kind="final")
