"""Shared enumerations. Mirrors docs/DATA_MODEL.md § Enumerations exactly."""
from enum import Enum


class DiseaseClass(str, Enum):
    healthy_leaf = "healthy_leaf"
    healthy_collar = "healthy_collar"
    foliar_yellowing = "foliar_yellowing"
    collar_lesion = "collar_lesion"
    defoliation_wilt = "defoliation_wilt"
    unrelated = "unrelated"
    unknown = "unknown"


class BlockState(str, Enum):
    protected = "protected"
    alerted = "alerted"
    harmed = "harmed"
    overrun = "overrun"


class ElevationTier(str, Enum):
    minimal = "minimal"
    optimised = "optimised"


class DrainageCondition(str, Enum):
    good = "good"
    fair = "fair"
    poor = "poor"


class SlopeCategory(str, Enum):
    gentle = "gentle"
    moderate = "moderate"
    steep = "steep"


class TreatmentType(str, Enum):
    contact = "contact"
    systemic = "systemic"
    biological = "biological"
    cultural = "cultural"


class ActionType(str, Enum):
    spray = "spray"
    drench = "drench"
    clear_drain = "clear_drain"
    isolate_vine = "isolate_vine"
    remove_vine = "remove_vine"
    inspect = "inspect"
    notify_neighbour = "notify_neighbour"
    no_action = "no_action"


class AlertStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    sent = "sent"
    dismissed = "dismissed"


class Language(str, Enum):
    ms = "ms"
    iba = "iba"
    en = "en"


class SyncStatus(str, Enum):
    local_only = "local_only"
    syncing = "syncing"
    synced = "synced"
    failed = "failed"


class KnowledgeNamespace(str, Enum):
    authoritative = "authoritative"
    advisory = "advisory"
    local = "local"


class CycleStatus(str, Enum):
    in_progress = "in_progress"
    complete = "complete"
    abandoned = "abandoned"


class AdvisorUrgency(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    none = "none"


class ElevationSource(str, Enum):
    farmer = "farmer"
    barometer = "barometer"
    dem = "dem"


class CaptureTarget(str, Enum):
    leaf = "leaf"
    collar = "collar"
    whole_vine = "whole_vine"


class DiagnosisTrigger(str, Enum):
    rain_pulse = "rain_pulse"
    stale = "stale"
    user_initiated = "user_initiated"
    agent_recommended = "agent_recommended"


class AgentRunTrigger(str, Enum):
    observation = "observation"
    scheduled = "scheduled"
    manual = "manual"
    setup_validation = "setup_validation"


class AgentRunStatus(str, Enum):
    ok = "ok"
    partial = "partial"
    failed = "failed"


class DeferCause(str, Enum):
    rainfast = "rainfast"
    spread_priority = "spread_priority"
    resource = "resource"


class WeatherSource(str, Enum):
    did_sarawak = "did_sarawak"
    data_gov_my = "data_gov_my"
