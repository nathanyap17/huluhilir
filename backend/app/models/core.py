"""users, farms, walk_sessions, walk_samples, blocks, flow_edges, elevation_conflicts.
docs/DATA_MODEL.md §1-7.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, now_kuching, ulid_pk


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = ulid_pk()
    display_name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    district: Mapped[str] = mapped_column(String(40))
    language_pref: Mapped[str] = mapped_column(String(4), default="ms")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)


class Farm(Base):
    __tablename__ = "farms"

    farm_id: Mapped[str] = ulid_pk()
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"))
    name: Mapped[str] = mapped_column(String(80))
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    weather_station_id: Mapped[Optional[str]] = mapped_column(String(30))
    elevation_tier: Mapped[str] = mapped_column(String(12), default="minimal")
    barometer_available: Mapped[bool] = mapped_column(Boolean, default=False)
    total_area_ha: Mapped[Optional[float]] = mapped_column(Float)
    setup_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    walk_session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("walk_sessions.walk_session_id"))

    blocks: Mapped[list["Block"]] = relationship(back_populates="farm")


class WalkSession(Base):
    __tablename__ = "walk_sessions"

    walk_session_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sample_interval_ms: Mapped[int] = mapped_column(Integer, default=2000)
    baseline_pressure_hpa: Mapped[Optional[float]] = mapped_column(Float)
    baseline_captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    total_samples: Mapped[int] = mapped_column(Integer, default=0)
    mean_gps_accuracy_m: Mapped[Optional[float]] = mapped_column(Float)


class WalkSample(Base):
    __tablename__ = "walk_samples"

    sample_id: Mapped[str] = ulid_pk()
    walk_session_id: Mapped[str] = mapped_column(ForeignKey("walk_sessions.walk_session_id"))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    gps_alt_m: Mapped[Optional[float]] = mapped_column(Float)
    gps_accuracy_m: Mapped[float] = mapped_column(Float)
    baro_alt_m: Mapped[Optional[float]] = mapped_column(Float)
    pressure_hpa: Mapped[Optional[float]] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Block(Base):
    """Central entity. `elevation_rank` unique per farm — ties break the graph."""

    __tablename__ = "blocks"

    block_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    label: Mapped[str] = mapped_column(String(30))
    voice_label_uri: Mapped[Optional[str]] = mapped_column(String(255))
    photo_uri: Mapped[str] = mapped_column(String(255))
    centroid_lat: Mapped[float] = mapped_column(Float)
    centroid_lon: Mapped[float] = mapped_column(Float)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
    elevation_rank: Mapped[int] = mapped_column(Integer)
    baro_rel_m: Mapped[Optional[float]] = mapped_column(Float)
    dem_elevation_m: Mapped[Optional[float]] = mapped_column(Float)
    slope_category: Mapped[Optional[str]] = mapped_column(String(10))
    drainage: Mapped[str] = mapped_column(String(4), default="fair")
    area_ha: Mapped[Optional[float]] = mapped_column(Float)
    vine_count: Mapped[Optional[int]] = mapped_column(Integer)
    variety: Mapped[Optional[str]] = mapped_column(String(40))
    current_state: Mapped[str] = mapped_column(String(10), default="protected")
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_diagnosis_id: Mapped[Optional[str]] = mapped_column(String(26))
    last_treated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    external_owner_name: Mapped[Optional[str]] = mapped_column(String(80))
    external_owner_phone: Mapped[Optional[str]] = mapped_column(String(20))

    farm: Mapped["Farm"] = relationship(back_populates="blocks")


class FlowEdge(Base):
    """Acyclic by construction: from.elevation_rank < to.elevation_rank always."""

    __tablename__ = "flow_edges"

    edge_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    from_block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    to_block_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    horizontal_dist_m: Mapped[float] = mapped_column(Float)
    elevation_drop_m: Mapped[Optional[float]] = mapped_column(Float)
    slope_ratio: Mapped[Optional[float]] = mapped_column(Float)
    flow_weight: Mapped[float] = mapped_column(Float)
    barrier: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20))
    farmer_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    conflict_logged: Mapped[bool] = mapped_column(Boolean, default=False)


class ElevationConflict(Base):
    """Exists to prove 'farmer is authoritative' is implemented, not merely asserted."""

    __tablename__ = "elevation_conflicts"

    conflict_id: Mapped[str] = ulid_pk()
    farm_id: Mapped[str] = mapped_column(ForeignKey("farms.farm_id"))
    block_a_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    block_b_id: Mapped[str] = mapped_column(ForeignKey("blocks.block_id"))
    farmer_says: Mapped[str] = mapped_column(String(20))
    barometer_says: Mapped[Optional[str]] = mapped_column(String(20))
    dem_says: Mapped[Optional[str]] = mapped_column(String(20))
    resolution: Mapped[str] = mapped_column(String(20), default="farmer")
    delta_h_m: Mapped[Optional[float]] = mapped_column(Float)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_kuching)
