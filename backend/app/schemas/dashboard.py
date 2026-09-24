"""`GET /farm/{farm_id}/dashboard` contract. docs/PROJECT_SPEC.md §7.

Every risk number carries `is_estimate`; every string carries a
`speech_template_id` — literacy is not assumed.
"""
from datetime import date as date_type
from typing import Optional

from pydantic import Field

from app.schemas.advisor import AdvisorVerdictOut
from app.schemas.agent import RecommendationOut
from app.schemas.common import ORMModel
from app.schemas.farm import BlockOut, FlowEdgeOut

# rainfall_mm at or above this counts as a "pulse" for DailyForecast.is_pulse
# and for picking which day the collapsed day_label/rainfall_mm view below
# highlights. Matches the >= 5.0mm threshold the v1 single-day rain_pulse
# already used (see the old get_dashboard before this file's Phase C edit).
PULSE_THRESHOLD_MM = 5.0


class DailyForecast(ORMModel):
    date: date_type
    rainfall_mm: float
    is_pulse: bool
    is_cached_fallback: bool


class RainPulseResponse(ORMModel):
    """🔄 v2 — was a single next-pulse object in v1 (docs/PROJECT_SPEC.md §9.1,
    §10). The underlying 7-day data already existed in GetWeatherResult.
    forecast_7d; nothing needed computing, only exposing what get_weather
    already returns instead of collapsing it to one day."""

    forecast_days: list[DailyForecast]
    station_id: str
    speech_template_id: Optional[str] = None


class TerrainNode(ORMModel):
    block_id: str
    elevation_rank: int
    current_state: str
    lat: float
    lon: float
    x_rot_m: float = Field(description="Rotated local-metre x, backend-computed (§3 L2 STEP 1-2)")
    y_rot_m: float = Field(description="Rotated local-metre y, backend-computed (§3 L2 STEP 1-2)")


class RecommendationDrawer(ORMModel):
    """§9.2's extensible drawer — 🔄 v2. Exposes risk_assessments columns that
    already existed in the schema but nothing wrote until Phase C
    (app/agent/runner.py's _extract_risk_assessments) or read back out."""

    risk_score: float
    confidence: float = Field(description="Input-quality, not disease certainty")
    eta_days: Optional[int] = None
    defer_cause: Optional[str] = None
    rainfall_7d_mm: float


class DashboardResponse(ORMModel):
    farm_id: str
    rain_pulse: RainPulseResponse
    advisor: Optional[AdvisorVerdictOut] = None
    top_action: Optional[RecommendationOut] = Field(
        default=None, description="actions[0] only — the arbitration result"
    )
    drawer: Optional[RecommendationDrawer] = Field(
        default=None, description="§9.2 — only present when a risk_assessments row exists for top_action's block"
    )
    terrain_nodes: list[TerrainNode]
    terrain_edges: list[FlowEdgeOut]
    pending_neighbour_alerts: int = 0
    blocks: list[BlockOut]
