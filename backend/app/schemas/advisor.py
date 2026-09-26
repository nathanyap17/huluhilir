"""Advisor verdict contract. docs/DATA_MODEL.md §18, docs/PROJECT_SPEC.md §6.

Computed at request time (`GET /farm/{id}/advisor`) — no background polling.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import AdvisorUrgency


class AdvisorVerdictOut(ORMModel):
    verdict_id: str = ulid_field()
    farm_id: str
    urgency: AdvisorUrgency
    reason_code: str = Field(max_length=30)
    reason_ms: str = Field(max_length=300)
    suggested_date: Optional[date] = None
    days_until_recommended: Optional[int] = None
    # 2026-09-27: when the next check is most useful, and why (app/tools/advisor.py next_best_check)
    next_check_basis: Optional[str] = Field(default=None, max_length=30)
    next_check_ms: Optional[str] = Field(default=None, max_length=300)
    next_check_en: Optional[str] = Field(default=None, max_length=300)
    last_cycle_at: Optional[datetime] = None
    last_cycle_result: Optional[str] = None
    days_since_last_cycle: int
    rain_since_last_cycle_mm: float
    blocks_all_protected: bool
    computed_at: datetime
