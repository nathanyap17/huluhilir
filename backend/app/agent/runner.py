"""Runs the RootAgent for one turn and persists the result.

This is the seam between ADK and the rest of the app: builds a fresh
RootAgent scoped to one DB session/farm, drives it with google.genai
Content, parses its final JSON recommendations, and writes agent_runs +
recommendations rows -- including tools_called, which must never be
dropped (docs/DATA_MODEL.md §15).
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

from google.adk.runners import InMemoryRunner
from google.genai import types
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import progress
from app.agent.advisor_agent import build_advisor_agent
from app.agent.council_agent import run_overrun_council
from app.agent.logging_callbacks import ToolCallLogger, _summarize
from app.agent.root_agent import build_root_agent
from app.config import settings
from app.models.agent import AgentRun, CalendarEventProposal, CouncilDebate, Recommendation

from app.models.base import KUCHING_TZ, now_kuching
from app.models.core import Block, Farm
from app.models.diagnosis import Diagnosis, RiskAssessment
from app.models.knowledge import TreatmentOption
from app.schemas.enums import ActionType, ElevationTier
from app.schemas.spread import ComputeSpreadRequest
from app.schemas.treatment import FindSprayWindowRequest, ForecastPoint
from app.tools.council import is_farm_overrun
from app.tools.spread import SOURCE_SEVERITY, SPREAD_MODEL_VERSION, load_farm_graph
from app.tools.spread import compute_spread as compute_spread_impl
from app.tools.scheduling import SCHEDULABLE, proposal_for, workable_slot
from app.tools.treatment import find_spray_window, get_treatment
from app.tools.weather import get_weather

APP_NAME = "pepperdex"

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(text: str) -> dict:
    """The model is instructed to emit ONLY JSON, but small local models
    occasionally wrap it in prose or a markdown fence anyway -- salvage the
    first {...} block rather than failing the whole run on that."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise
        return json.loads(match.group(0))


_RAINFAST_GATED_ACTIONS = {"spray", "drench"}


def _reconcile_spray_deferrals(recommendations_data: list[dict], calls: list[dict]) -> list[dict]:
    """Deterministic safety net over the LLM's arbitration, not a replacement
    for it (google-adk skill: loop/termination logic is deterministic Python,
    never LLM judgement -- extended here to the rainfast defer decision
    specifically, because empirical testing showed qwen2.5:14b unreliably
    incorporates find_spray_window's defer_cause into its final JSON even
    when explicitly instructed to (see docs/BUILD_LOG.md § Block C for the
    observed failure: 5 identical "treat now" recommendations with
    defer_cause=null despite find_spray_window returning rain_free=False for
    every near-term window). This function overrides defer_cause and
    recommended_at for rainfast-gated actions using find_spray_window's
    ACTUAL last-called result, and injects a clear_drain recommendation
    ahead of any deferred spray if the model didn't already produce one --
    "drainage before spraying when water movement is the dominant risk"
    (docs/PROJECT_SPEC.md §3 L4) enforced structurally, not hoped for.
    """
    spray_calls = [c for c in calls if c["name"] == "find_spray_window"]
    if not spray_calls:
        return recommendations_data

    raw = spray_calls[-1].get("_raw_result") or {}
    result = raw.get("result", raw) if isinstance(raw, dict) else {}
    if not isinstance(result, dict) or "defer_cause" not in result:
        return recommendations_data

    actual_defer_cause = result.get("defer_cause")
    recommended_window = result.get("recommended_window")

    reconciled = []
    needs_drainage_first = False
    for rec in recommendations_data:
        rec = dict(rec)
        if rec.get("action_type") in _RAINFAST_GATED_ACTIONS and rec.get("treatment_id"):
            rec["defer_cause"] = actual_defer_cause
            # The real computed window always wins over anything the model
            # wrote for recommended_at -- observed failure mode was the model
            # fabricating an unrelated date (e.g. "2023-10-06") even when
            # defer_cause was correctly None and a real window existed.
            if recommended_window and recommended_window.get("window_start"):
                rec["recommended_at"] = recommended_window["window_start"]
            if actual_defer_cause == "rainfast":
                needs_drainage_first = True
        reconciled.append(rec)

    if needs_drainage_first and not any(r.get("action_type") == "clear_drain" for r in reconciled):
        first_block_id = reconciled[0]["block_id"] if reconciled else None
        if first_block_id:
            for r in reconciled:
                r["sequence"] = r.get("sequence", 1) + 1
            reconciled.insert(0, {
                "block_id": first_block_id,
                "sequence": 1,
                "action_type": "clear_drain",
                "treatment_id": None,
                "recommended_at": now_kuching().isoformat(),
                "reason_ms": "Buka parit sekarang -- hujan dijangka dalam tempoh tahan hujan racun.",
                "defer_cause": None,
            })

    return reconciled


def _extract_risk_assessments(
    calls: list[dict], run_id: str, cycle_id: Optional[str], inputs: Optional[dict] = None
) -> list[RiskAssessment]:
    """Turns compute_spread's actual tool result into risk_assessments rows.

    Nothing wrote this table before Phase C -- `compute_spread` returned a
    result the arbitration turn used in-memory and then discarded, so the
    action drawer (docs/PROJECT_SPEC.md §9.2 drawer.risk_score/confidence/
    eta_days/rainfall_7d_mm) had no real data to expose. This reads the same
    ACTUAL result already captured for _reconcile_spray_deferrals, rather
    than re-deriving anything -- one source of truth for what the tool
    really returned, not a second guess at it.
    """
    rows: list[RiskAssessment] = []
    for call in calls:
        if call["name"] != "compute_spread":
            continue
        raw = call.get("_raw_result") or {}
        result = raw.get("result", raw) if isinstance(raw, dict) else {}
        if not isinstance(result, dict) or "results" not in result:
            continue

        args = call.get("args", {})
        source_block_id = result.get("source_block_id", args.get("source_block_id"))
        is_estimate = result.get("is_estimate", True)

        for item in result["results"]:
            rows.append(RiskAssessment(
                run_id=run_id,
                cycle_id=cycle_id,
                block_id=item["block_id"],
                source_block_id=source_block_id,
                risk_score=item["risk"],
                risk_band=item["risk_band"],
                eta_days=item.get("eta_days"),
                path_block_ids=item.get("path"),
                confidence=item["confidence"],
                rainfall_7d_mm=args.get("rainfall_7d_mm", (inputs or {}).get("rainfall_7d_mm", 0.0)),
                forecast_7d_mm=args.get("forecast_7d_mm", (inputs or {}).get("forecast_7d_mm", 0.0)),
                elevation_tier_used=args.get("elevation_tier", (inputs or {}).get("elevation_tier", "minimal")),
                model_version=SPREAD_MODEL_VERSION,
                is_estimate=is_estimate,
            ))
    return rows


def _apply_council_ranking(recommendations_data: list[dict], ranking: list[dict]) -> list[dict]:
    """'If the council produced a ranking, follow its block order when
    sequencing' (docs/PROJECT_SPEC.md §3 L4 RootAgent instruction, step 4).

    Deterministic, same reasoning as _reconcile_spray_deferrals: a local
    model unreliably threading a second agent's output back into its own
    JSON is an already-observed failure mode (see that function's
    docstring for the defer_cause precedent) -- so this re-sequences
    Python-side rather than hoping the arbitration turn's prose respected
    the ranking it was shown.
    """
    rank_by_block = {r["block_id"]: r["rank"] for r in ranking}
    reordered = []
    for rec in recommendations_data:
        rec = dict(rec)
        if rec["block_id"] in rank_by_block:
            rec["sequence"] = rank_by_block[rec["block_id"]]
        reordered.append(rec)
    return reordered


async def _farm_blocks(session: AsyncSession, farm_id: str) -> list[Block]:
    return (
        await session.execute(
            select(Block)
            .where(Block.farm_id == farm_id, Block.is_external.is_(False))
            .order_by(Block.elevation_rank.desc())
        )
    ).scalars().all()


async def _latest_diagnoses(
    session: AsyncSession, farm_id: str, cycle_id: Optional[str]
) -> list[tuple[Block, Diagnosis]]:
    """(block, its latest diagnosis) for blocks diagnosed in this cycle."""
    out = []
    for block in await _farm_blocks(session, farm_id):
        if not block.last_diagnosis_id:
            continue
        diag = await session.get(Diagnosis, block.last_diagnosis_id)
        if diag is None or (cycle_id and diag.cycle_id != cycle_id):
            continue
        out.append((block, diag))
    return out


async def _deterministic_recommendations(
    session: AsyncSession, farm_id: str, cycle_id: Optional[str]
) -> list[dict]:
    """Rules-table-only arbitration, used when the LLM turn times out or fails.

    Same authority as the LLM path (pepperdex-rules 2): product and timing come
    from get_treatment / find_spray_window and nothing else; no model writes a
    dose. It is less nuanced than the agent (no council, no spread reasoning,
    one treatment per block), which is why the run is marked `partial` and a
    `deterministic_fallback` entry is written to tools_called.
    """
    blocks = await _farm_blocks(session, farm_id)

    weather = get_weather(farm_id)
    forecast = [
        ForecastPoint(forecast_date=str(f.forecast_date), rainfall_mm=f.rainfall_mm, probability=f.probability)
        for f in weather.forecast_7d
    ]
    now_iso = now_kuching().replace(tzinfo=None).isoformat()

    recs: list[dict] = []
    for block, diag in await _latest_diagnoses(session, farm_id, cycle_id):
        cls = diag.predicted_class
        if cls in ("healthy_leaf", "healthy_collar") and not diag.below_threshold:
            continue
        if diag.below_threshold or cls in ("unrelated", "unknown"):
            recs.append({
                "block_id": block.block_id, "action_type": "inspect", "treatment_id": None,
                "recommended_at": now_iso, "defer_cause": None,
                "reason_ms": f"Periksa {block.label} secara fizikal -- keyakinan diagnosis rendah.",
            })
            continue

        options = (await get_treatment(session, cls)).options
        if not options:
            recs.append({
                "block_id": block.block_id, "action_type": "inspect", "treatment_id": None,
                "recommended_at": now_iso, "defer_cause": None,
                "reason_ms": f"Periksa {block.label} -- tiada rawatan dalam jadual untuk keadaan ini.",
            })
            continue

        option = options[0]
        window = find_spray_window(FindSprayWindowRequest(
            treatment_id=option.treatment_id, rainfast_hours=option.rainfast_hours, forecast=forecast,
        ))
        action = str(getattr(option.application_method, "value", option.application_method))
        if window.defer_cause == "rainfast":
            recs.append({
                "block_id": block.block_id, "action_type": "clear_drain", "treatment_id": None,
                "recommended_at": now_iso, "defer_cause": None,
                "reason_ms": f"Bersihkan parit di {block.label} dahulu; hujan dijangka sebelum semburan sempat kering.",
            })
        when = window.recommended_window.window_start.isoformat() if window.recommended_window else now_iso
        recs.append({
            "block_id": block.block_id, "action_type": action, "treatment_id": option.treatment_id,
            "recommended_at": when, "defer_cause": window.defer_cause,
            "reason_ms": (
                f"{option.name_ms} di {block.label}."
                if window.defer_cause is None
                else f"Tangguh {option.name_ms} di {block.label}: hujan dijangka dalam tempoh tahan hujan."
            ),
        })

    if not recs and blocks:
        recs.append({
            "block_id": blocks[0].block_id, "action_type": "no_action", "treatment_id": None,
            "recommended_at": now_iso, "defer_cause": None,
            "reason_ms": "Tiada tindakan diperlukan buat masa ini.",
        })
    for i, rec in enumerate(recs, start=1):
        rec["sequence"] = i
    return recs


def _call_result(call: dict) -> dict:
    raw = call.get("_raw_result") or {}
    res = raw.get("result", raw) if isinstance(raw, dict) else {}
    return res if isinstance(res, dict) else {}


async def _deterministic_spread(
    session: AsyncSession, farm_id: str, cycle_id: Optional[str], tool_logger: ToolCallLogger
) -> None:
    """compute_spread is deterministic (L2 is not ML), so run it for every
    diseased source block the LLM did not already project with a real block
    id. Without this, a fallback run -- or a run where the model passed a
    hallucinated source id ('block-123', observed 2026-09-23) -- had no
    risk_assessments rows, and a startup seed routine used to paper over that
    with constant 0.85/0.92/45.2 values (rule 8 violation, removed). Each call
    is logged like an agent tool call so tools_called stays the record.
    """
    blocks = await _farm_blocks(session, farm_id)
    valid_ids = {b.block_id for b in blocks}
    projected = {
        _call_result(c).get("source_block_id")
        for c in tool_logger.calls
        if c["name"] == "compute_spread" and _call_result(c).get("source_block_id") in valid_ids
    }
    farm = await session.get(Farm, farm_id)
    tier = (farm.elevation_tier if farm else None) or "minimal"
    weather = get_weather(farm_id)
    rain_past = round(sum(o.rainfall_mm for o in weather.rainfall_7d), 1)
    rain_ahead = round(sum(f.rainfall_mm for f in weather.forecast_7d), 1)
    graph = None
    for block, diag in await _latest_diagnoses(session, farm_id, cycle_id):
        if block.block_id in projected or SOURCE_SEVERITY.get(diag.predicted_class, 0.0) <= 0:
            continue
        graph = graph or await load_farm_graph(session, farm_id)
        args = {
            "source_block_id": block.block_id,
            "source_class": diag.predicted_class,
            "rainfall_7d_mm": rain_past,
            "forecast_7d_mm": rain_ahead,
            "elevation_tier": tier,
        }
        result = compute_spread_impl(ComputeSpreadRequest(
            farm_graph=graph, **{**args, "elevation_tier": ElevationTier(tier)}
        ))
        call = {
            "name": "compute_spread",
            "args": {**args, "invoked_by": "runner_deterministic"},
            "latency_ms": 0,
            "result_summary": _summarize(result),
            "_raw_result": result.model_dump(mode="json"),
        }
        tool_logger.calls.append(call)
        tool_logger.emit_call(call)


async def _guard_llm_recommendations(
    session: AsyncSession, farm_id: str, cycle_id: Optional[str], recs: list, tool_logger: ToolCallLogger
) -> list[dict]:
    """Deterministic check of the model's plan against the rules table, same
    family as _reconcile_spray_deferrals. Observed 2026-09-23 on qwen2.5:14b:
    one run marked `ok` returned zero recommendations; another answered
    `no_action`/`inspect` for two blocks diagnosed with collar lesion, dated
    2023-10-11. The farmer saw no proposal cards and a stale priority action.
    This:
      - drops recs naming a block not on this farm, an unknown action, or a
        treatment_id absent from the rules table (rule 2);
      - replaces unparseable or stale (over a day in the past) dates with now;
      - adds the rules-table action for any diseased block the model left
        untreated, removing a contradicting no_action for that block.
    Every correction is written to tools_called as `rules_guard`.
    """
    blocks = await _farm_blocks(session, farm_id)
    valid_ids = {b.block_id for b in blocks}
    valid_actions = {a.value for a in ActionType}
    treatment_ids = set((await session.execute(select(TreatmentOption.treatment_id))).scalars().all())
    now = now_kuching().replace(tzinfo=None)

    kept: list[dict] = []
    dropped = stale = 0
    for rec in recs if isinstance(recs, list) else []:
        if (
            not isinstance(rec, dict)
            or rec.get("block_id") not in valid_ids
            or rec.get("action_type") not in valid_actions
            or (rec.get("treatment_id") and rec["treatment_id"] not in treatment_ids)
        ):
            dropped += 1
            continue
        try:
            when = datetime.fromisoformat(str(rec.get("recommended_at")).replace("Z", "+00:00"))
            if when.tzinfo is not None:
                when = when.astimezone(KUCHING_TZ).replace(tzinfo=None)
        except ValueError:
            when = None
        if when is None or when < now - timedelta(days=1):
            stale += 1
            rec = {**rec, "recommended_at": now.isoformat()}
        kept.append(dict(rec))

    baseline = await _deterministic_recommendations(session, farm_id, cycle_id)
    treated = {r["block_id"] for r in kept if r["action_type"] in ("spray", "drench")}
    handled = {r["block_id"] for r in kept if r["action_type"] != "no_action"}
    missing = {
        b["block_id"]
        for b in baseline
        if (b["action_type"] in ("spray", "drench") and b["block_id"] not in treated)
        or (b["action_type"] == "inspect" and b["block_id"] not in handled)
    }
    if missing:
        kept = [r for r in kept if not (r["block_id"] in missing and r["action_type"] == "no_action")]
        kept += [b for b in baseline if b["block_id"] in missing and b["action_type"] != "no_action"]
    if not kept:
        kept = baseline

    for i, rec in enumerate(kept, start=1):
        rec["sequence"] = i

    if dropped or stale or missing:
        labels = {b.block_id: b.label for b in blocks}
        miss = ", ".join(labels[b] for b in sorted(missing))
        note_ms = "; ".join(filter(None, [
            f"{dropped} cadangan tidak sah dibuang" if dropped else "",
            f"{stale} tarikh lapuk dibetulkan" if stale else "",
            f"rawatan jadual peraturan ditambah untuk {miss}" if missing else "",
        ]))
        note_en = "; ".join(filter(None, [
            f"dropped {dropped} invalid item(s)" if dropped else "",
            f"fixed {stale} stale date(s)" if stale else "",
            f"added rules-table treatment for {miss}" if missing else "",
        ]))
        call = {
            "name": "rules_guard",
            "args": {"dropped": dropped, "stale_dates": stale, "added_for": sorted(missing),
                     "note_ms": note_ms, "note_en": note_en},
            "latency_ms": 0,
            "result_summary": note_en,
        }
        tool_logger.calls.append(call)
        tool_logger.emit_call(call)
    return kept


async def _emit_intro(session: AsyncSession, run_id: str, farm_id: str, cycle_id: Optional[str]) -> None:
    """DiagnosisCoordinator's message: what the photo loop actually captured."""
    diags = await _latest_diagnoses(session, farm_id, cycle_id)
    if not diags:
        return
    parts_ms, parts_en = [], []
    for block, d in sorted(diags, key=lambda bd: bd[0].elevation_rank):
        c_ms, c_en = progress.CLASS_LABEL.get(d.predicted_class, (d.predicted_class, d.predicted_class))
        pct = round(d.confidence * 100)
        low_ms = " -- keyakinan rendah" if d.below_threshold else ""
        low_en = " -- low confidence" if d.below_threshold else ""
        parts_ms.append(f"{block.label}: {c_ms} ({pct}%){low_ms}")
        parts_en.append(f"{block.label}: {c_en} ({pct}%){low_en}")
    progress.emit(
        run_id, "diagnosis_coordinator",
        f"Gambar semua {len(diags)} blok diambil. Keputusan CNN:\n" + "\n".join(parts_ms),
        f"All {len(diags)} blocks photographed. CNN results:\n" + "\n".join(parts_en),
    )


async def run_root_agent(
    session: AsyncSession,
    farm_id: str,
    user_message: str,
    cycle_id: Optional[str] = None,
    trigger: str = "manual",
    agent_run_id: Optional[str] = None,
) -> AgentRun:
    """Runs one RootAgent turn and persists agent_runs + recommendations.
    Caller is responsible for session.commit() and progress.finish().

    `agent_run_id`: an AgentRun row the caller already committed (background
    mode, so the client can poll /agent/runs/{id}/events straight away)."""
    started_at = now_kuching()

    # The run row exists from the start so the live feed, the council's FK and
    # the final record all share one run_id.
    agent_run = await session.get(AgentRun, agent_run_id) if agent_run_id else None
    if agent_run is None:
        agent_run = AgentRun(
            farm_id=farm_id, trigger=trigger, cycle_id=cycle_id, tools_called=[],
            llm_model=settings.litellm_model, started_at=started_at, status="running",
        )
        session.add(agent_run)
        await session.flush()
    run_id = agent_run.run_id
    if progress.get(run_id) is None:
        progress.start(run_id)
    labels = {b.block_id: b.label for b in await _farm_blocks(session, farm_id)}
    await _emit_intro(session, run_id, farm_id, cycle_id)

    # Step 3a (docs/PROJECT_SPEC.md §3 L4): farm_state == 'overrun' AND more
    # than one block simultaneously Harmed -> delegate to the council BEFORE
    # arbitrating. Detected deterministically (app/tools/council.py), not
    # left to the LLM to notice -- same reasoning as every other
    # deterministic gate in this file.
    overrun, harmed_blocks = await is_farm_overrun(session, farm_id)
    council_ranking: Optional[list[dict]] = None
    council_note = ""
    if overrun:
        agent_run.subagent_invoked = "overrun_council"
        progress.emit(
            run_id, "root_agent",
            f"{len(harmed_blocks)} blok terjejas serentak -- Majlis Triaj (4 ejen) dipanggil untuk menyusun keutamaan.",
            f"{len(harmed_blocks)} blocks harmed at once -- convening the Overrun Council (4 agents) to rank them.",
        )
        progress.set_current(run_id, "council_orchestrator", "Majlis sedang berbahas…", "The council is debating…")
        try:
            council_ranking = await asyncio.wait_for(
                run_overrun_council(session, farm_id, agent_run.run_id, harmed_blocks),
                timeout=settings.agent_timeout_s,
            )
        except Exception as exc:  # council is advisory ordering only; never block the run on it
            logger.warning("overrun council failed (%s); continuing without a ranking", type(exc).__name__)
            council_ranking = None
        await session.flush()
        debate = (
            await session.execute(select(CouncilDebate).where(CouncilDebate.run_id == run_id))
        ).scalars().first()
        if debate is not None:
            for turn in debate.transcript or []:
                if turn.get("argument"):
                    agent_key = progress.COUNCIL_AGENT.get(turn.get("agent", ""), "council_orchestrator")
                    progress.emit(run_id, agent_key, turn["argument"], turn["argument"], kind="debate")
        if council_ranking:
            order = sorted(council_ranking, key=lambda r: r["rank"])
            chain = " > ".join(labels.get(r["block_id"], "?") for r in order)
            progress.emit(
                run_id, "council_orchestrator",
                f"Susunan triaj: {chain}. " + (order[0].get("rationale_ms") or ""),
                f"Triage order: {chain}. (Ranks only -- the schema cannot hold a dose or product.)",
                kind="debate",
            )
    if council_ranking:
        ranked_labels = ", ".join(
            f"{r['block_id']} (rank {r['rank']})"
            for r in sorted(council_ranking, key=lambda r: r["rank"])
        )
        council_note = (
            f"\n\nThe Overrun Council has already triage-ranked the currently harmed blocks "
            f"(order to treat first -> last): {ranked_labels}. Follow this order when sequencing "
            "your recommendations for these blocks -- do not re-rank them yourself, and never invent "
            "a treatment, dose, or timing from the council's ranking; get_treatment remains the only "
            "source of that."
        )

    tool_logger = ToolCallLogger()
    tool_logger.progress_run_id = run_id
    tool_logger.block_labels = labels
    model_name = settings.litellm_model.split("/")[-1]
    progress.set_current(
        run_id, "root_agent",
        f"RootAgent ({model_name}) sedang menimbang cuaca, aliran dan peraturan…",
        f"RootAgent ({model_name}) is weighing weather, spread and rules…",
    )
    root_agent = build_root_agent(session, farm_id, cycle_id=cycle_id, tool_logger=tool_logger)

    adk_runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    user_id, session_id = f"farm_{farm_id}", f"run_{farm_id}"
    await adk_runner.session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

    async def _drive() -> str:
        text = ""
        async for event in adk_runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=user_message + council_note)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts)
        return text

    # The LLM turn is bounded. A local model can hang far past what a farmer
    # will wait (observed 2026-09-20: litellm.Timeout after 600 s against
    # Ollama qwen2.5:14b, no Recommendation rows written, so the Home cards
    # never updated). On timeout or any LLM/transport error we fall back to
    # the deterministic rules-table path below rather than failing the run.
    final_text = ""
    llm_failure: Optional[str] = None
    try:
        final_text = await asyncio.wait_for(_drive(), timeout=settings.agent_timeout_s)
    except asyncio.TimeoutError:
        llm_failure = f"llm_timeout_{settings.agent_timeout_s}s"
    except Exception as exc:  # litellm.Timeout / connection refused / ADK errors
        llm_failure = f"llm_error_{type(exc).__name__}"
    if llm_failure:
        logger.warning("agent run for farm %s fell back to deterministic path: %s", farm_id, llm_failure)

    status = "ok"
    recommendations_data = []
    if llm_failure is None:
        try:
            parsed = _extract_json(final_text)
            recommendations_data = parsed.get("recommendations", [])
        except (json.JSONDecodeError, AttributeError):
            status = "partial"

    if llm_failure is None and not recommendations_data:
        llm_failure = "empty_llm_output" if status == "ok" else "unparseable_llm_output"

    if llm_failure is not None:
        status = "partial"
        recommendations_data = await _deterministic_recommendations(session, farm_id, cycle_id)
        tool_logger.calls.append({
            "name": "deterministic_fallback",
            "args": {"reason": llm_failure},
            "latency_ms": 0,
            "result_summary": f"{len(recommendations_data)} recommendation(s) from rules table only",
        })
        tool_logger.emit_call(tool_logger.calls[-1])
    else:
        recommendations_data = await _guard_llm_recommendations(
            session, farm_id, cycle_id, recommendations_data, tool_logger
        )

    progress.set_current(run_id, "spread_model", "Mengesahkan unjuran aliran…", "Confirming spread projections…")
    await _deterministic_spread(session, farm_id, cycle_id, tool_logger)

    recommendations_data = _reconcile_spray_deferrals(recommendations_data, tool_logger.calls)
    if council_ranking is not None:
        recommendations_data = _apply_council_ranking(recommendations_data, council_ranking)

    agent_run.tools_called = tool_logger.public_calls()
    agent_run.completed_at = now_kuching()
    agent_run.status = status
    await session.flush()

    # A new diagnosis supersedes schedule proposals nobody acted on yet, so the
    # Advisor never shows two competing plans for the same blocks.
    stale_props = (
        await session.execute(
            select(CalendarEventProposal).where(
                CalendarEventProposal.farm_id == farm_id,
                CalendarEventProposal.status == "pending_approval",
            )
        )
    ).scalars().all()
    for old in stale_props:
        old.status = "superseded"

    # One slot rule for everything the farmer will see (card, decision
    # message, calendar proposal): field hours, never "right now", never 00:00.
    for rec in recommendations_data:
        if rec.get("action_type") in SCHEDULABLE and not rec.get("defer_cause"):
            rec["recommended_at"] = workable_slot(
                datetime.fromisoformat(str(rec["recommended_at"]).replace("Z", "+00:00"))
            ).isoformat()

    proposals_made = 0
    for rec in recommendations_data:
        rec_row = Recommendation(
            run_id=agent_run.run_id,
            block_id=rec["block_id"],
            sequence=rec.get("sequence", 1),
            action_type=rec["action_type"],
            treatment_id=rec.get("treatment_id"),
            recommended_at=datetime.fromisoformat(rec["recommended_at"]),
            reason_ms=rec.get("reason_ms", ""),
            defer_cause=rec.get("defer_cause"),
        )
        session.add(rec_row)
        await session.flush()

        # Phase 3 Autonomous Scheduling: Proactively formulate a Calendar Proposal (Rule 13 Guardrail)
        # Never writes to Google Calendar automatically; farmer approval is strictly required.
        if rec["action_type"] in SCHEDULABLE and not rec.get("defer_cause"):
            proposal = proposal_for(
                farm_id=farm_id,
                run_id=agent_run.run_id,
                recommendation_id=rec_row.recommendation_id,
                block=await session.get(Block, rec["block_id"]),
                action_type=rec["action_type"],
                start=datetime.fromisoformat(rec["recommended_at"]),
                reason_ms=rec.get("reason_ms", ""),
            )
            session.add(proposal)
            proposals_made += 1

    projected_up: list[str] = []
    _w = get_weather(farm_id)
    _farm = await session.get(Farm, farm_id)
    spread_inputs = {
        "rainfall_7d_mm": round(sum(o.rainfall_mm for o in _w.rainfall_7d), 1),
        "forecast_7d_mm": round(sum(f.rainfall_mm for f in _w.forecast_7d), 1),
        "elevation_tier": (_farm.elevation_tier if _farm else None) or "minimal",
    }
    for assessment in _extract_risk_assessments(tool_logger.calls, agent_run.run_id, cycle_id, spread_inputs):
        session.add(assessment)
        # docs/PROJECT_SPEC.md "Block state model", rule 2: L2 may project a
        # block UP (protected -> alerted) with zero photos of it; rule 3: an
        # improving projection never downgrades. Nothing did this before, so
        # "Alerted" only ever appeared via a yellowing-leaf photo.
        if assessment.risk_band in ("alerted", "harmed") and assessment.block_id in labels:
            target = await session.get(Block, assessment.block_id)
            if target is not None and target.current_state == "protected":
                target.current_state = "alerted"
                target.state_changed_at = now_kuching()
                projected_up.append(labels[assessment.block_id])
    if projected_up:
        names = ", ".join(sorted(set(projected_up)))
        progress.emit(
            run_id, "spread_model",
            f"{names} kini Diberi amaran (unjuran aliran dari blok di atas cerun, tiada gambar diperlukan).",
            f"{names} now Alerted (projected from upslope; no photo of it needed).",
        )

    plan =progress.describe_plan(recommendations_data, labels)
    progress.emit(run_id, plan["agent"], plan["text_ms"], plan["text_en"], plan["kind"])
    if proposals_made:
        progress.emit(
            run_id, "calendar_mcp",
            f"{proposals_made} cadangan jadual menunggu kelulusan anda. "
            "Tiada apa ditulis ke Google Calendar sebelum anda luluskan.",
            f"{proposals_made} schedule proposal(s) await your approval. "
            "Nothing is written to Google Calendar until you approve.",
            kind="approval",
        )
    return agent_run


async def run_advisor_question(
    session: AsyncSession,
    question: str,
    farm_id: Optional[str] = None,
    history: Optional[list[dict]] = None,
) -> dict:
    """Answer one free-form "Tanya" question via the Advisor agent.

    Deliberately *not* persisted as an agent_run: agent_runs record decisions
    that produced recommendations, and a farmer asking "what causes foot rot"
    produced none. Mixing the two would corrupt the arbitration audit trail
    that `tools_called` exists to evidence.

    The Advisor's only tool is retrieve_knowledge, hard-scoped away from the
    authoritative namespace, so this path structurally cannot emit a dose,
    product, or timing (pepperdex-rules §2) -- that is enforced by what the
    agent can reach, not by asking the model nicely.
    """
    from app.tools.farm_context import build_farm_context

    tool_logger = ToolCallLogger()
    advisor = build_advisor_agent(session, tool_logger=tool_logger)

    # Farm memory: a DB snapshot of THIS farm + the recent chat turns, so a
    # follow-up like "are the blocks safer now?" is answered about the
    # farmer's own blocks instead of the model asking what crop they grow.
    parts: list[str] = []
    if farm_id:
        context = await build_farm_context(session, farm_id)
        if context:
            parts.append("FARM CONTEXT (from the PepperDex database -- authoritative for this farm):\n" + context)
    turns = [h for h in (history or []) if isinstance(h, dict) and h.get("text")][-8:]
    if turns:
        parts.append("CONVERSATION SO FAR:\n" + "\n".join(
            f"{'Farmer' if h.get('role') == 'user' else 'Advisor'}: {str(h['text'])[:400]}" for h in turns
        ))
    parts.append("FARMER'S QUESTION: " + question)
    message = "\n\n".join(parts)

    adk_runner = InMemoryRunner(agent=advisor, app_name=APP_NAME)
    user_id, session_id = "advisor_user", f"ask_{abs(hash(message)) % 10_000_000}"
    await adk_runner.session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    async def _ask() -> str:
        text = ""
        async for event in adk_runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts)
        return text

    try:
        answer = await asyncio.wait_for(_ask(), timeout=settings.agent_timeout_s)
    except Exception as exc:  # timeout / model down: say so instead of hanging
        logger.warning("advisor question failed: %s", type(exc).__name__)
        answer = ""

    return {
        "question": question,
        "answer": answer.strip(),
        "sources": [
            c.get("result_summary", "")[:200]
            for c in tool_logger.public_calls()
            if c.get("name") == "retrieve_knowledge"
        ],
        "tools_called": tool_logger.public_calls(),
        "llm_model": settings.litellm_model,
    }
