"""User, farm, walk-session, block and flow-edge contracts. docs/DATA_MODEL.md §1-7."""
from datetime import datetime
from typing import Optional

from pydantic import Field

from app.schemas.common import ORMModel, ulid_field
from app.schemas.enums import (
    DrainageCondition,
    ElevationSource,
    ElevationTier,
    Language,
    SlopeCategory,
)


class UserCreate(ORMModel):
    display_name: str = Field(max_length=80)
    phone: Optional[str] = Field(default=None, max_length=20)
    district: str = Field(max_length=40)
    language_pref: Language = Language.ms


class UserOut(UserCreate):
    user_id: str = ulid_field()
    created_at: datetime


class FarmCreate(ORMModel):
    user_id: str
    name: str = Field(max_length=80)
    centroid_lat: float
    centroid_lon: float
    weather_station_id: Optional[str] = None
    barometer_available: bool = False
    total_area_ha: Optional[float] = None


class FarmOut(FarmCreate):
    farm_id: str = ulid_field()
    elevation_tier: ElevationTier
    setup_completed_at: Optional[datetime] = None
    walk_session_id: Optional[str] = None


class WalkSessionCreate(ORMModel):
    farm_id: str
    sample_interval_ms: int = 2000


class WalkSessionOut(WalkSessionCreate):
    walk_session_id: str = ulid_field()
    started_at: datetime
    ended_at: Optional[datetime] = None
    baseline_pressure_hpa: Optional[float] = None
    baseline_captured_at: Optional[datetime] = None
    total_samples: int = 0
    mean_gps_accuracy_m: Optional[float] = None


class WalkSampleCreate(ORMModel):
    walk_session_id: str
    lat: float
    lon: float
    gps_alt_m: Optional[float] = None
    gps_accuracy_m: float
    baro_alt_m: Optional[float] = None
    pressure_hpa: Optional[float] = None
    recorded_at: datetime


class BlockCreate(ORMModel):
    farm_id: str
    label: str = Field(max_length=30, description="Farmer's own words")
    voice_label_uri: Optional[str] = None
    photo_uri: str
    centroid_lat: float
    centroid_lon: float
    drainage: DrainageCondition = DrainageCondition.fair
    area_ha: Optional[float] = None
    vine_count: Optional[int] = None
    variety: Optional[str] = Field(default=None, max_length=40)
    is_external: bool = False
    external_owner_name: Optional[str] = Field(default=None, max_length=80)
    external_owner_phone: Optional[str] = Field(default=None, max_length=20)


class BlockOut(BlockCreate):
    block_id: str = ulid_field()
    marked_at: datetime
    elevation_rank: int = Field(description="1 = highest. Unique per farm")
    baro_rel_m: Optional[float] = None
    dem_elevation_m: Optional[float] = None
    slope_category: Optional[SlopeCategory] = None
    current_state: str = "protected"
    state_changed_at: Optional[datetime] = None
    last_diagnosis_id: Optional[str] = None
    last_treated_at: Optional[datetime] = None


class FlowEdgeOut(ORMModel):
    edge_id: str = ulid_field()
    farm_id: str
    from_block_id: str
    to_block_id: str
    horizontal_dist_m: float
    elevation_drop_m: Optional[float] = None
    slope_ratio: Optional[float] = None
    flow_weight: float = Field(ge=0, le=1)
    barrier: bool = False
    source: ElevationSource
    farmer_confirmed: bool = False
    conflict_logged: bool = False


class ElevationConflictOut(ORMModel):
    conflict_id: str = ulid_field()
    farm_id: str
    block_a_id: str
    block_b_id: str
    farmer_says: str
    barometer_says: Optional[str] = None
    dem_says: Optional[str] = None
    resolution: str = "farmer"
    delta_h_m: Optional[float] = None
    logged_at: datetime
