"""Calendar sync contracts. docs/PROJECT_SPEC.md §3 L4, §9.15, §10, DATA_MODEL.md §23.

pepperdex-rules skill §13: draft_calendar_sync produces text; it never writes
to a calendar directly. The actual device write is 100% client-side
(expo-calendar) -- this backend's job is the draft text and the consent
record (calendar_sync_grants), never the write itself.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import CalendarProvider


class DraftCalendarEvent(ORMModel):
    title: str
    date: date
    description: str


class DraftCalendarSyncResult(ORMModel):
    draft_events: list[DraftCalendarEvent]


class CalendarSyncGrantOut(ORMModel):
    grant_id: str = ulid_field()
    farm_id: str
    provider: CalendarProvider
    granted_at: datetime
    revoked_at: Optional[datetime] = None


class CalendarGrantRequest(ORMModel):
    provider: CalendarProvider = Field(default=CalendarProvider.device_calendar)


class CalendarGrantStatus(ORMModel):
    granted: bool
    grant: Optional[CalendarSyncGrantOut] = None

class CreateCalendarEventRequest(ORMModel):
    title: str = Field(..., max_length=120)
    start_iso: str
    end_iso: Optional[str] = None
    description: str = ""
    location: str = "Ladang Lada (Pepper Block)"


class CalendarProposalOut(ORMModel):
    proposal_id: str = ulid_field()
    farm_id: str
    run_id: Optional[str] = None
    recommendation_id: Optional[str] = None
    title: str
    start_time: datetime
    end_time: datetime
    description: str
    location: str
    status: str
    approved_by_farmer: bool
    approved_at: Optional[datetime] = None
    google_event_id: Optional[str] = None
    html_link: Optional[str] = None
    created_at: datetime


class ApproveProposalRequest(ORMModel):
    farmer_confirmed: bool = Field(default=True)

