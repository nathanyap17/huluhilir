"""Builds the ADK FunctionTool list for the RootAgent.

IMPORTANT -- every tool function below takes FLATTENED scalar/list parameters,
never a single Pydantic request model as the whole parameter. The installed
google-adk (2.7.1) flattens a lone `req: SomeModel` parameter's fields into
the top-level tool schema shown to the LLM (via the JSON_SCHEMA_FOR_FUNC_DECL
feature), but `FunctionTool._prepare_invocation_args` does NOT reconstruct
the model back from those flattened args before calling the function -- it
only rebuilds a Pydantic value when the arg dict already has a key matching
the parameter's own name. The net effect: `def f(req: SomeModel)` receives
call args like `{"query": ..., "top_k": ...}` with no `req` key at all, and
every invocation fails with "mandatory input parameters are not present:
req". `list[SomeModel]` parameters ARE reconstructed correctly (there's
explicit handling for that shape) -- only the bare single-model-as-whole-
parameter shape is broken. See docs/BUILD_LOG.md § Block C for the full
diagnosis; verified against `google/adk/tools/function_tool.py` in this
exact venv, not just the adk-python skill reference clone.

`compute_spread` also never asks the LLM to construct the farm_graph -- that
is combinatorial computation the machine already holds (docs/PROJECT_SPEC.md
§3 L2), loaded via load_farm_graph() from the DB instead.
"""
from google.adk.tools import FunctionTool
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.error_boundary import tool_error_boundary
from app.agent.llm_tools import draft_alert_flat, draft_calendar_sync_flat, explain_why_flat
from app.models.core import Block, Farm
from app.models.diagnosis import Diagnosis
from app.schemas.diagnosis import DiagnoseLeafResult
from app.schemas.enums import CaptureTarget, ElevationTier
from app.schemas.spread import ComputeSpreadRequest, ComputeSpreadResult
from app.schemas.treatment import FindSprayWindowResult, ForecastPoint, GetTreatmentResult
from app.schemas.weather import GetWeatherResult
from app.tools.diagnose import diagnose_leaf as diagnose_leaf_impl
from app.tools.farm_history import query_farm_history as query_farm_history_impl
from app.tools.spread import compute_spread as compute_spread_impl
from app.tools.spread import load_farm_graph
from app.tools.treatment import find_spray_window as find_spray_window_impl
from app.tools.treatment import get_treatment as get_treatment_impl
from app.tools.weather import get_weather as get_weather_impl
from app.tools import calendar_service
from app.agent import mcp_calendar_client


@tool_error_boundary
def diagnose_leaf(observation_id: str, image_uri: str, capture_target: str) -> DiagnoseLeafResult:
    """Classify a leaf/collar photo into one of six disease states using the
    trained CNN. capture_target must be 'leaf', 'collar', or 'whole_vine'.
    Returns confidence and a mismatch_flag if the photo doesn't match what
    capture_target claims it is. confidence < 0.60 means advise a physical
    inspection -- never assert a diagnosis on a low-confidence result."""
    return diagnose_leaf_impl(observation_id, image_uri, CaptureTarget(capture_target))


@tool_error_boundary
def get_weather(farm_id: str) -> GetWeatherResult:
    """Get the last 7 days of rainfall and the next 7 days of forecast for a
    farm. Always check is_cached_fallback -- when true, the live weather API
    was unavailable and this is offline cached data."""
    return get_weather_impl(farm_id)


@tool_error_boundary
async def check_calendar_schedule(max_results: int = 10) -> dict:
    """Check upcoming events on the farmer's linked Google Calendar.
    Use this to see upcoming scheduled farm tasks or detect potential scheduling
    conflicts before suggesting a treatment date. Returns events or connection status."""
    try:
        mcp_res = await mcp_calendar_client.mcp_list_upcoming_events(max_results=max_results)
        return {
            "connected": True,
            "mcp_output": mcp_res,
        }
    except Exception as exc:
        return {
            "connected": False,
            "error": str(exc),
        }


@tool_error_boundary
async def check_calendar_availability(start_iso: str, end_iso: str) -> dict:
    """Check if the farmer is available during a specific treatment window.
    Use this to ensure a proposed spray or drench window does not conflict with existing events."""
    try:
        mcp_res = await mcp_calendar_client.mcp_check_availability(start_iso=start_iso, end_iso=end_iso)
        return {
            "connected": True,
            "mcp_output": mcp_res,
        }
    except Exception as exc:
        return {
            "connected": False,
            "error": str(exc),
        }


@tool_error_boundary
async def schedule_treatment_event(
    title: str,
    start_iso: str,
    end_iso: str | None = None,
    description: str = "",
    location: str = "Ladang Lada (Pepper Block)",
) -> dict:
    """Schedule a confirmed treatment or farm event into Google Calendar.
    RULE 13 (Human-in-the-Loop): Do NOT call this tool unless the farmer has explicitly
    approved or instructed to schedule the event in the calendar. Otherwise propose a plan first.
    Requires Google Calendar to be connected."""
    try:
        mcp_res = await mcp_calendar_client.mcp_create_calendar_event(
            title=title,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description,
            location=location,
        )
        success = "Error" not in mcp_res and "failed" not in mcp_res.lower()
        return {
            "success": success,
            "mcp_output": mcp_res,
            "message": "Berjaya dijadualkan." if success else "Gagal dijadualkan.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "message": f"Gagal menjadualkan acara: {exc}",
        }



@tool_error_boundary
async def reschedule_treatment_event(
    event_id: str,
    new_start_iso: str,
    new_end_iso: str | None = None,
    new_title: str | None = None,
    new_description: str | None = None,
) -> dict:
    """Reschedule an existing Google Calendar event using MCP when rain forecast changes."""
    if not calendar_service.is_calendar_connected():
        return {
            "success": False,
            "message": "Google Calendar is not connected.",
        }
    try:
        mcp_res = await mcp_calendar_client.mcp_update_calendar_event(
            event_id=event_id,
            new_title=new_title,
            new_start_iso=new_start_iso,
            new_end_iso=new_end_iso,
            new_description=new_description,
        )
        return {
            "success": "SUCCESS" in mcp_res,
            "mcp_output": mcp_res,
            "message": f"Acara '{event_id}' berjaya dijadualkan semula.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


@tool_error_boundary
async def cancel_treatment_event(event_id: str) -> dict:
    """Cancel and remove a treatment event from Google Calendar using MCP."""
    if not calendar_service.is_calendar_connected():
        return {
            "success": False,
            "message": "Google Calendar is not connected.",
        }
    try:
        mcp_res = await mcp_calendar_client.mcp_delete_calendar_event(event_id=event_id)
        return {
            "success": "SUCCESS" in mcp_res,
            "mcp_output": mcp_res,
            "message": f"Acara '{event_id}' berjaya dipadamkan dari Google Calendar.",
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
        }


def build_tools(session: AsyncSession, farm_id: str) -> list[FunctionTool]:
    @tool_error_boundary
    async def compute_spread(source_block_id: str) -> ComputeSpreadResult:
        """Project downhill disease spread from ONE diagnosed block across the
        farm's elevation graph. Pass only the block_id of a block that was
        diagnosed with disease. Deterministic, not machine learning -- every
        result carries is_estimate=True. Call it once per diseased block,
        after all blocks in the cycle are captured."""
        # Only the block id comes from the model. The disease class, the 7-day
        # rain totals and the elevation tier are data the server already
        # holds -- asking the model to supply them failed on every observed
        # local run (2026-09-24): rainfall sent as -9999 or as the literal
        # text "${weather.rainfall_7d}", class sent as "harmed_leaf". Same
        # principle as never letting the model build the farm graph.
        block = await session.get(Block, source_block_id)
        if block is None or block.farm_id != farm_id:
            raise ValueError(f"unknown block_id {source_block_id!r} -- use a block_id from this farm")
        diag = await session.get(Diagnosis, block.last_diagnosis_id) if block.last_diagnosis_id else None
        if diag is None:
            raise ValueError(f"block {source_block_id} has no diagnosis yet -- nothing to project from")
        farm = await session.get(Farm, farm_id)
        weather = get_weather_impl(farm_id)
        graph = await load_farm_graph(session, farm_id)
        req = ComputeSpreadRequest(
            source_block_id=source_block_id,
            source_class=diag.predicted_class,
            farm_graph=graph,
            rainfall_7d_mm=round(sum(o.rainfall_mm for o in weather.rainfall_7d), 1),
            forecast_7d_mm=round(sum(f.rainfall_mm for f in weather.forecast_7d), 1),
            elevation_tier=ElevationTier((farm.elevation_tier if farm else None) or "minimal"),
        )
        return compute_spread_impl(req)

    @tool_error_boundary
    async def get_treatment(predicted_class: str) -> GetTreatmentResult:
        """Look up approved treatments for a diagnosed disease class from the
        rules table. This is the ONLY source of dose, product, and timing --
        never invent a treatment that isn't in this result. May return an
        empty options list if no treatment applies (e.g. for a healthy class)."""
        return await get_treatment_impl(session, predicted_class)

    @tool_error_boundary
    async def find_spray_window(treatment_id: str) -> FindSprayWindowResult:
        """Find when a treatment from get_treatment can be applied without rain
        washing it off. Pass only its treatment_id. If defer_cause is
        'rainfast' in the result there is NO safe window yet -- do not
        recommend spraying now; defer it and put drainage work first."""
        # The rain-fast hours come from the rules table and the forecast from
        # get_weather -- never from the model. Observed 2026-09-24: qwen
        # passed an invented forecast dated 2023-09-01, and a model that
        # omits rainfast_hours would silently skip the wash-off check.
        from app.models.knowledge import TreatmentOption
        from app.schemas.treatment import FindSprayWindowRequest

        option = await session.get(TreatmentOption, treatment_id)
        if option is None:
            raise ValueError(f"unknown treatment_id {treatment_id!r} -- use one returned by get_treatment")
        weather = get_weather_impl(farm_id)
        forecast = [
            ForecastPoint(forecast_date=str(f.forecast_date), rainfall_mm=f.rainfall_mm, probability=f.probability)
            for f in weather.forecast_7d
        ]
        req = FindSprayWindowRequest(treatment_id=treatment_id, rainfast_hours=option.rainfast_hours, forecast=forecast)
        return find_spray_window_impl(req)

    @tool_error_boundary
    async def query_farm_history(
        block_id: str | None = None,
        disease_class: str | None = None,
        since_days: int | None = None,
        limit: int = 20,
    ) -> dict:
        """Look up REAL past diagnoses, risk_assessments, and recommendations
        for this farm -- direct rows, never a paraphrase. Use this to answer
        "what happened before" questions (e.g. "has this block been treated
        recently", "what was the last risk score here") instead of guessing
        from memory. All filters are optional. Never returns a dose or
        product beyond what a past recommendation already recorded -- this
        reads history, it does not decide a new treatment."""
        return await query_farm_history_impl(
            session, farm_id,
            block_id=block_id, disease_class=disease_class, since_days=since_days, limit=limit,
        )

    return [
        FunctionTool(func=diagnose_leaf),
        FunctionTool(func=get_weather),
        FunctionTool(func=compute_spread),
        FunctionTool(func=get_treatment),
        FunctionTool(func=find_spray_window),
        FunctionTool(func=query_farm_history),
        FunctionTool(func=tool_error_boundary(explain_why_flat)),
        FunctionTool(func=tool_error_boundary(draft_alert_flat)),
        FunctionTool(func=tool_error_boundary(draft_calendar_sync_flat)),
        FunctionTool(func=check_calendar_schedule),
        FunctionTool(func=check_calendar_availability),
        # schedule/reschedule/cancel_treatment_event are deliberately NOT given
        # to the model (removed 2026-09-24): they wrote to Google Calendar with
        # no farmer approval, bypassing rule 13. The only write path is the
        # farmer approving a CalendarEventProposal card
        # (routers/calendar.py approve_calendar_proposal). Reads stay.
    ]

