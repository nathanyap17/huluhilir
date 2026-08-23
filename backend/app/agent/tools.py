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
from app.agent.llm_tools import draft_alert_flat, explain_why_flat
from app.schemas.diagnosis import DiagnoseLeafResult
from app.schemas.enums import CaptureTarget, ElevationTier
from app.schemas.spread import ComputeSpreadRequest, ComputeSpreadResult
from app.schemas.treatment import FindSprayWindowResult, ForecastPoint, GetTreatmentResult
from app.schemas.weather import GetWeatherResult
from app.tools.diagnose import diagnose_leaf as diagnose_leaf_impl
from app.tools.spread import compute_spread as compute_spread_impl
from app.tools.spread import load_farm_graph
from app.tools.treatment import find_spray_window as find_spray_window_impl
from app.tools.treatment import get_treatment as get_treatment_impl
from app.tools.weather import get_weather as get_weather_impl


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


def build_tools(session: AsyncSession, farm_id: str) -> list[FunctionTool]:
    @tool_error_boundary
    async def compute_spread(
        source_block_id: str, source_class: str, rainfall_7d_mm: float, forecast_7d_mm: float, elevation_tier: str
    ) -> ComputeSpreadResult:
        """Project downhill disease spread across the farm's elevation graph
        from a diagnosed source block. Deterministic, not machine learning --
        every result carries is_estimate=True. Call this ONCE after all
        blocks in a diagnosis cycle are captured, not per block (partial
        projection causes flapping recommendations). elevation_tier is
        'minimal' or 'optimised'.

        rainfall_7d_mm and forecast_7d_mm MUST be the real numbers returned
        by a prior get_weather call for this farm -- never a placeholder or
        guessed value. If you have not called get_weather yet in this
        conversation, call it first and wait for its result before calling
        this tool."""
        graph = await load_farm_graph(session, farm_id)
        req = ComputeSpreadRequest(
            source_block_id=source_block_id,
            source_class=source_class,
            farm_graph=graph,
            rainfall_7d_mm=rainfall_7d_mm,
            forecast_7d_mm=forecast_7d_mm,
            elevation_tier=ElevationTier(elevation_tier),
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
    def find_spray_window(
        treatment_id: str, forecast: list[ForecastPoint], rainfast_hours: int | None = None
    ) -> FindSprayWindowResult:
        """Given a treatment's rainfast_hours (from get_treatment) and a
        rainfall forecast, find viable spray windows where no rain falls
        before the product has had time to work. If defer_cause is
        'rainfast' in the result, there is NO safe window yet -- do not
        recommend spraying; defer it and prioritise drainage work if water
        movement is the risk. forecast items need date, rainfall_mm,
        and optionally probability."""
        from app.schemas.treatment import FindSprayWindowRequest
        req = FindSprayWindowRequest(treatment_id=treatment_id, rainfast_hours=rainfast_hours, forecast=forecast)
        return find_spray_window_impl(req)

    return [
        FunctionTool(func=diagnose_leaf),
        FunctionTool(func=get_weather),
        FunctionTool(func=compute_spread),
        FunctionTool(func=get_treatment),
        FunctionTool(func=find_spray_window),
        FunctionTool(func=tool_error_boundary(explain_why_flat)),
        FunctionTool(func=tool_error_boundary(draft_alert_flat)),
    ]
