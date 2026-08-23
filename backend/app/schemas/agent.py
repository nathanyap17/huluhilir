"""Agent orchestration contracts: runs, recommendations, alerts, and the two
LLM-backed tools (`explain_why`, `draft_alert`). docs/DATA_MODEL.md §15-17.

`tools_called` must never be cut — it is the demo evidence of visible
orchestration (docs/PROJECT_SPEC.md §3 L4).
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import ActionType, AgentRunStatus, AgentRunTrigger, BlockState, DeferCause


class ToolCallLogEntry(ORMModel):
    name: str
    args: dict[str, Any]
    latency_ms: int
    result_summary: str


class AgentRunOut(ORMModel):
    run_id: str = ulid_field()
    farm_id: str
    trigger: AgentRunTrigger
    cycle_id: Optional[str] = None
    tools_called: list[ToolCallLogEntry] = Field(default_factory=list)
    subagent_invoked: Optional[str] = Field(default=None, max_length=40)
    llm_model: str
    token_count: Optional[int] = None
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: AgentRunStatus = AgentRunStatus.ok


class RecommendationOut(ORMModel):
    recommendation_id: str = ulid_field()
    run_id: str
    block_id: str
    sequence: int = Field(description="1 = do first (drain before spray)")
    action_type: ActionType
    treatment_id: Optional[str] = None
    recommended_at: datetime = Field(description="When to do it, not when generated")
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    reason_ms: str = Field(max_length=300, description="One sentence. Mandatory.")
    speech_template_id: Optional[str] = None
    deferred_from: Optional[datetime] = None
    defer_cause: Optional[DeferCause] = None
    confidence_note: Optional[str] = Field(default=None, max_length=120)


class AlertOut(ORMModel):
    alert_id: str = ulid_field()
    run_id: str
    target_block_id: str
    recipient_name: Optional[str] = None
    recipient_phone: Optional[str] = None
    message_ms: str
    risk_band_shared: BlockState = Field(description="Only this is shared with the neighbour")
    status: str = "draft"
    approved_by_farmer: bool = Field(default=False, description="Never auto-true")
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None


# ---- LLM-backed tools: generation only, never decision -----------------------

class ExplainWhyRequest(ORMModel):
    recommendation: RecommendationOut
    supporting_facts: dict[str, Any] = Field(
        description="e.g. {'diagnosis': ..., 'rainfast_hours': ..., 'forecast_mm': ..., 'eta_days': ...}"
    )


class ExplainWhyResult(ORMModel):
    reason_ms: str = Field(max_length=300)


class DraftAlertRequest(ORMModel):
    target_block_id: str
    risk_band: BlockState
    source_farm_name: str


class DraftAlertResult(ORMModel):
    message_ms: str
    risk_band_shared: BlockState
