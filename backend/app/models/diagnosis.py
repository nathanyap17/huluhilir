"""diagnosis_cycles, observations, diagnoses, risk_assessments. docs/DATA_MODEL.md §8-11."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, now_kuching, ulid_pk


class DiagnosisCycle(Base):
    """A diagnosis is an event covering all blocks, not a per-photo action. Resumable."""

    __tablename__ = "diagnosis_cycles"

    cycle_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    trigger_reason: Mapped[str] = mapped_column(String(30))
    triggering_rain_mm: Mapped[Optional[float]] = mapped_column(Float)
    triggering_rain_date: Mapped[Optional[str]] = mapped_column(String(10))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    blocks_total: Mapped[int] = mapped_column(Integer)
    blocks_captured: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="in_progress")
    run_id: Mapped[Optional[str]] = mapped_column(String(26))


class Observation(Base):
    __tablename__ = "observations"

    observation_id: Mapped[str] = ulid_pk()
    cycle_id: Mapped[Optional[str]] = mapped_column(ForeignKey("diagnosis_cycles.cycle_id"))
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    image_uri: Mapped[str] = mapped_column(String(255))
    image_hash: Mapped[str] = mapped_column(String(64))
    capture_target: Mapped[str] = mapped_column(String(20))
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gps_lat: Mapped[Optional[float]] = mapped_column(Float)
    gps_lon: Mapped[Optional[float]] = mapped_column(Float)
    sync_status: Mapped[str] = mapped_column(String(12), default="local_only")


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    diagnosis_id: Mapped[str] = ulid_pk()
    observation_id: Mapped[str] = mapped_column(ForeignKey("observations.observation_id"), unique=True)
    cycle_id: Mapped[Optional[str]] = mapped_column(ForeignKey("diagnosis_cycles.cycle_id"))
    predicted_class: Mapped[str] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    all_scores: Mapped[dict] = mapped_column(JSON)
    second_class: Mapped[Optional[str]] = mapped_column(String(20))
    below_threshold: Mapped[bool] = mapped_column(Boolean)
    model_version: Mapped[str] = mapped_column(String(20))
    inference_ms: Mapped[Optional[int]] = mapped_column(Integer)


class RiskAssessment(Base):
    """One row per block per run — a time series, not current state."""

    __tablename__ = "risk_assessments"

    assessment_id: Mapped[str] = ulid_pk()
    run_id: Mapped[str] = mapped_column(String(26))
    cycle_id: Mapped[Optional[str]] = mapped_column(ForeignKey("diagnosis_cycles.cycle_id"))
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    source_block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    risk_score: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(10))
    eta_days: Mapped[Optional[int]] = mapped_column(Integer)
    path_block_ids: Mapped[Optional[list]] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float)
    rainfall_7d_mm: Mapped[float] = mapped_column(Float)
    forecast_7d_mm: Mapped[float] = mapped_column(Float)
    elevation_tier_used: Mapped[str] = mapped_column(String(12))
    model_version: Mapped[str] = mapped_column(String(20))
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
