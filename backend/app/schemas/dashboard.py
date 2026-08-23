"""`GET /farm/{farm_id}/dashboard` contract. docs/PROJECT_SPEC.md §7.

Every risk number carries `is_estimate`; every string carries a
`speech_template_id` — literacy is not assumed.
"""
from typing import Optional

from pydantic import Field

from app.schemas.advisor import AdvisorVerdictOut
from app.schemas.agent import RecommendationOut
from app.schemas.common import ORMModel
from app.schemas.farm import BlockOut, FlowEdgeOut


class RainPulse(ORMModel):
    day_label: str
    rainfall_mm: float
    days_away: int
    speech_template_id: Optional[str] = None


class TerrainNode(ORMModel):
    block_id: str
    elevation_rank: int
    current_state: str
    lat: float
    lon: float


class DashboardResponse(ORMModel):
    farm_id: str
    rain_pulse: RainPulse
    advisor: Optional[AdvisorVerdictOut] = None
    top_action: Optional[RecommendationOut] = Field(
        default=None, description="actions[0] only — the arbitration result"
    )
    terrain_nodes: list[TerrainNode]
    terrain_edges: list[FlowEdgeOut]
    pending_neighbour_alerts: int = 0
    blocks: list[BlockOut]
