"""Global config Pydantic schema for ASRE configuration (SPEC §4.2)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CustomerConfig(BaseModel):
    """Customer identification."""

    customer_id: str
    customer_name: str


class WarehouseConfig(BaseModel):
    """Warehouse connection configuration."""

    type: str
    connection: dict[str, Any]


class ScheduleConfig(BaseModel):
    """Schedule and run mode configuration."""

    mode: str = "incremental"
    lookback_buffer: dict[str, str] = {
        "default": "24h",
        "adt": "24h",
        "claims": "72h",
        "auth": "24h",
    }


class EncounterStitchingConfig(BaseModel):
    """Encounter stitching rules."""

    time_window_hours: int = 48
    facility_must_match: bool = True
    patient_class_transitions: list[dict[str, str]] = [
        {"from": "ed", "to": "inpatient", "action": "merge"},
        {"from": "observation", "to": "inpatient", "action": "merge"},
        {"from": "inpatient", "to": "inpatient", "action": "new_encounter"},
    ]
    same_timestamp_tiebreaker: list[str] = ["claims", "adt", "auth"]


class DeduplicationConfig(BaseModel):
    """Deduplication settings."""

    match_fields: list[str] = [
        "patient_key",
        "event_type",
        "facility_canonical_id",
    ]
    time_tolerance_minutes: int = 30


class ReconciliationConfig(BaseModel):
    """Cross-source reconciliation settings."""

    timestamp_priority: dict[str, int] = {
        "adt": 100,
        "claims": 80,
        "auth": 40,
    }
    classification_priority: dict[str, int] = {
        "claims": 100,
        "adt": 80,
        "auth": 40,
    }
    timestamp_tolerance_hours: int = 24


class EpisodeStitchingConfig(BaseModel):
    """Episode stitching rules."""

    readmission_window_days: int = 30
    post_acute_linkage_days: int = 14
    planned_return_days: int = 90
    ed_bounceback_days: int = 7


class FacilityNormalizationConfig(BaseModel):
    """Facility normalization settings."""

    fuzzy_threshold: float = 0.85
    abbreviations: dict[str, str] = {
        "MED CTR": "MEDICAL CENTER",
        "MED": "MEDICAL",
        "CTR": "CENTER",
        "HOSP": "HOSPITAL",
        "HSP": "HOSPITAL",
        "HLTH": "HEALTH",
        "SYS": "SYSTEM",
        "REHAB": "REHABILITATION",
        "PSYCH": "PSYCHIATRIC",
        "COMM": "COMMUNITY",
        "GENL": "GENERAL",
        "GEN": "GENERAL",
        "REGL": "REGIONAL",
        "REG": "REGIONAL",
        "UNIV": "UNIVERSITY",
        "ST": "SAINT",
        "MT": "MOUNT",
    }


class ConfidenceScoringConfig(BaseModel):
    """Confidence scoring weights and penalties."""

    signal_weights: dict[str, int] = {
        "HAS_CLAIMS": 30,
        "HAS_ADT_ADMIT": 20,
        "HAS_ADT_DISCHARGE": 10,
        "HAS_AUTH": 10,
        "FACILITY_RESOLVED": 5,
        "TIMESTAMPS_CONSISTENT": 15,
        "PATIENT_CLASS_CONSISTENT": 10,
    }
    penalties: dict[str, float] = {
        "MISSING_DISCHARGE": -0.15,
        "ORPHAN_DISCHARGE": -0.20,
        "TIMESTAMP_MISMATCH": -0.10,
        "CLAIMS_ONLY_ENCOUNTER": -0.10,
        "STALE_OPEN_ENCOUNTER": -0.20,
        "DUPLICATE_DETECTED": -0.05,
        "FACILITY_UNRESOLVED": -0.10,
        "AUTH_WITHOUT_ADMIT": -0.05,
        "CANCELLED_AND_REOPENED": -0.05,
    }
    stale_encounter_thresholds: dict[str, int] = {
        "acute": 30,
        "ed_standalone": 3,
        "ltach": 90,
        "snf": 120,
        "rehab": 60,
        "psych": 90,
        "default": 30,
    }


class AlertingConfig(BaseModel):
    """Alerting and quality threshold configuration."""

    webhook_urls: list[str] = []
    thresholds: dict[str, float] = {
        "duplicate_rate_warn": 0.05,
        "duplicate_rate_fail": 0.15,
        "missing_discharge_rate_warn": 0.10,
        "missing_discharge_rate_fail": 0.25,
        "reconciliation_mismatch_rate_warn": 0.10,
        "reconciliation_mismatch_rate_fail": 0.25,
        "low_confidence_rate_warn": 0.15,
        "low_confidence_rate_fail": 0.30,
        "facility_unresolved_rate_warn": 0.05,
        "facility_unresolved_rate_fail": 0.15,
        "failed_event_rate_warn": 0.02,
        "failed_event_rate_fail": 0.05,
    }


class GlobalConfig(BaseModel):
    """Top-level ASRE configuration combining all sub-configs."""

    customer: CustomerConfig
    warehouse: WarehouseConfig
    schedule: ScheduleConfig = ScheduleConfig()
    encounter_stitching: EncounterStitchingConfig = EncounterStitchingConfig()
    deduplication: DeduplicationConfig = DeduplicationConfig()
    reconciliation: ReconciliationConfig = ReconciliationConfig()
    episode_stitching: EpisodeStitchingConfig = EpisodeStitchingConfig()
    facility_normalization: FacilityNormalizationConfig = FacilityNormalizationConfig()
    confidence_scoring: ConfidenceScoringConfig = ConfidenceScoringConfig()
    alerting: AlertingConfig = AlertingConfig()
    sources: list[Any] = []
    facility_aliases: Any | None = None
