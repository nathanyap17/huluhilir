"""Diagnosis cycle, observation and `diagnose_leaf` tool contracts. docs/DATA_MODEL.md §8-10."""
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import CaptureTarget, CycleStatus, DiagnosisTrigger, DiseaseClass, SyncStatus


class DiagnosisCycleCreate(ORMModel):
    farm_id: str
    trigger_reason: DiagnosisTrigger
    triggering_rain_mm: Optional[float] = None
    triggering_rain_date: Optional[str] = None
    blocks_total: int


class DiagnosisCycleOut(DiagnosisCycleCreate):
    cycle_id: str = ulid_field()
    started_at: datetime
    completed_at: Optional[datetime] = None
    blocks_captured: int = 0
    status: CycleStatus = CycleStatus.in_progress
    run_id: Optional[str] = None


class ObservationCreate(ORMModel):
    cycle_id: Optional[str] = None
    block_id: str
    user_id: str
    image_uri: str
    image_hash: str = Field(max_length=64, description="SHA-256, dedup")
    capture_target: CaptureTarget
    captured_at: datetime
    gps_lat: Optional[float] = None
    gps_lon: Optional[float] = None
    # The farmer overriding a retake prompt. They are standing in front of the
    # vine and the classifier is not -- the same principle as the farmer's
    # elevation answer beating the barometer (huluhilir-rules section 3).
    force_accept: bool = False


class ObservationOut(ObservationCreate):
    observation_id: str = ulid_field()
    sync_status: SyncStatus = SyncStatus.local_only


# ---- diagnose_leaf tool: the L1 ONNX inference contract ----------------------

class DiagnoseLeafRequest(ORMModel):
    observation_id: str
    image_uri: str
    capture_target: CaptureTarget


class DiagnoseLeafResult(ORMModel):
    diagnosis_id: str = ulid_field()
    observation_id: str
    predicted_class: DiseaseClass
    confidence: float = Field(ge=0, le=1)
    all_scores: dict[str, float] = Field(description="Full softmax over 6 classes")
    second_class: Optional[DiseaseClass] = None
    below_threshold: bool = Field(description="confidence < 0.60 -> advise physical inspection")
    model_version: str
    inference_ms: Optional[int] = None
    mismatch_flag: Optional[str] = Field(
        default=None,
        description="Set when predicted class contradicts capture_target (e.g. RETAKE: aim at the stem base)",
    )
