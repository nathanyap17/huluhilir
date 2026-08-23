"""`compute_spread` tool contract and `risk_assessments` schema. docs/PROJECT_SPEC.md §3 L2, docs/DATA_MODEL.md §11."""
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import BlockState, ElevationTier


class FarmGraphNode(ORMModel):
    block_id: str
    elevation_rank: int


class FarmGraphEdge(ORMModel):
    from_block_id: str
    to_block_id: str
    flow_weight: float = Field(ge=0, le=1)
    barrier: bool = False


class FarmGraph(ORMModel):
    nodes: list[FarmGraphNode]
    edges: list[FarmGraphEdge]


class ComputeSpreadRequest(ORMModel):
    source_block_id: str
    source_class: str = Field(description="Predicted DiseaseClass at the source block")
    farm_graph: FarmGraph
    rainfall_7d_mm: float
    forecast_7d_mm: float


class SpreadResultItem(ORMModel):
    block_id: str
    risk: float = Field(ge=0, le=1)
    risk_band: BlockState
    eta_days: Optional[int] = None
    path: list[str] = Field(description="block_ids from source to this block")
    confidence: float = Field(ge=0, le=1, description="Input quality, not disease certainty")


class ComputeSpreadResult(ORMModel):
    source_block_id: str
    results: list[SpreadResultItem]
    is_estimate: bool = True


class RiskAssessmentOut(ORMModel):
    assessment_id: str = ulid_field()
    run_id: str
    cycle_id: Optional[str] = None
    block_id: str
    source_block_id: str
    risk_score: float = Field(ge=0, le=1)
    risk_band: BlockState
    eta_days: Optional[int] = None
    path_block_ids: Optional[list[str]] = None
    confidence: float
    rainfall_7d_mm: float
    forecast_7d_mm: float
    elevation_tier_used: ElevationTier
    model_version: str
    is_estimate: bool = True
    computed_at: datetime
