"""`get_treatment` / `find_spray_window` tool contracts. docs/DATA_MODEL.md §12-13.

Hard rule (docs/CLAUDE.md § Non-negotiable rules #2): the rules table is the
only source of dose, product and timing. The agent may never output a
treatment absent from `TreatmentOptionOut`.
"""
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import ActionType, DiseaseClass, TreatmentType


class TreatmentOptionOut(ORMModel):
    treatment_id: str = Field(max_length=30, description="slug, primary key")
    name_ms: str
    name_en: str
    type: TreatmentType
    applies_to: list[DiseaseClass]
    rainfast_hours: Optional[int] = Field(default=None, description="Drives spray-window logic")
    dose_text_ms: Optional[str] = Field(default=None, description="Verbatim from source")
    application_method: ActionType
    reentry_hours: Optional[int] = None
    source_ref: str = Field(description="Mandatory citation")
    source_url: Optional[str] = None


class GetTreatmentRequest(ORMModel):
    predicted_class: DiseaseClass


class GetTreatmentResult(ORMModel):
    predicted_class: DiseaseClass
    options: list[TreatmentOptionOut]


class ForecastPoint(ORMModel):
    date: str
    rainfall_mm: float
    probability: Optional[float] = None


class FindSprayWindowRequest(ORMModel):
    treatment_id: str
    forecast: list[ForecastPoint]


class SprayWindow(ORMModel):
    window_start: datetime
    window_end: datetime
    rain_free: bool


class FindSprayWindowResult(ORMModel):
    treatment_id: str
    rainfast_hours: Optional[int]
    viable_windows: list[SprayWindow]
    recommended_window: Optional[SprayWindow] = None
    defer_cause: Optional[str] = Field(
        default=None, description="Set to 'rainfast' when no window clears before the next rain pulse"
    )


class TreatmentApplicationCreate(ORMModel):
    block_id: str
    treatment_id: str
    applied_at: datetime
    followed_recommendation: Optional[bool] = None
    recommendation_id: Optional[str] = None


class TreatmentApplicationOut(TreatmentApplicationCreate):
    application_id: str = ulid_field()
    rain_within_rainfast: Optional[bool] = Field(
        default=None, description="Outcome signal, computed after — powers the 'terbazir' (wasted) indicator"
    )
    rainfall_after_mm: Optional[float] = None
