"""agent_runs, recommendations, alerts, advisor_verdicts. docs/DATA_MODEL.md §15-18.

Keep `tools_called` and show it in the demo — visible orchestration convinces
judges more than a named protocol.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, now_kuching, ulid_pk


class AgentRun(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    trigger: Mapped[str] = mapped_column(String(20))
    cycle_id: Mapped[Optional[str]] = mapped_column(ForeignKey("diagnosis_cycles.cycle_id"))
    tools_called: Mapped[list] = mapped_column(JSON, default=list)
    subagent_invoked: Mapped[Optional[str]] = mapped_column(String(40))
    llm_model: Mapped[str] = mapped_column(String(40))
    token_count: Mapped[Optional[int]] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), default="ok")


class Recommendation(Base):
    """`deferred_from` + `defer_cause` are the arbitration record."""

    __tablename__ = "recommendations"

    recommendation_id: Mapped[str] = ulid_pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"))
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    sequence: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(20))
    treatment_id: Mapped[Optional[str]] = mapped_column(ForeignKey("treatment_options.treatment_id"))
    recommended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reason_ms: Mapped[str] = mapped_column(String(300))
    speech_template_id: Mapped[Optional[str]] = mapped_column(String(30))
    deferred_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    defer_cause: Mapped[Optional[str]] = mapped_column(String(20))
    confidence_note: Mapped[Optional[str]] = mapped_column(String(120))


class Alert(Base):
    __tablename__ = "alerts"

    alert_id: Mapped[str] = ulid_pk()
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.run_id"))
    target_block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    recipient_name: Mapped[Optional[str]] = mapped_column(String(80))
    recipient_phone: Mapped[Optional[str]] = mapped_column(String(20))
    message_ms: Mapped[str] = mapped_column(Text)
    risk_band_shared: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="draft")
    approved_by_farmer: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AdvisorVerdict(Base):
    __tablename__ = "advisor_verdicts"

    verdict_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    urgency: Mapped[str] = mapped_column(String(10))
    reason_code: Mapped[str] = mapped_column(String(30))
    reason_ms: Mapped[str] = mapped_column(String(300))
    suggested_date: Mapped[Optional[date]] = mapped_column(Date)
    days_until_recommended: Mapped[Optional[int]] = mapped_column(Integer)
    last_cycle_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_cycle_result: Mapped[Optional[str]] = mapped_column(String(20))
    days_since_last_cycle: Mapped[int] = mapped_column(Integer)
    rain_since_last_cycle_mm: Mapped[float] = mapped_column(Float)
    blocks_all_protected: Mapped[bool] = mapped_column(Boolean)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
