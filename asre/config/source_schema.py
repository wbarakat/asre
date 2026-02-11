"""Source config Pydantic schema for per-source mapping configs (SPEC §4.1)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator


class SourceDefinition(BaseModel):
    """Source table reference and incremental key."""

    table: str
    incremental_key: str


class FieldMappings(BaseModel):
    """Maps source columns to canonical event fields."""

    patient_key: str
    event_ts: str
    source_record_id: str
    facility_raw: str | None = None
    patient_class: str | None = None
    payer_id: str | None = None
    drg: str | None = None
    principal_diagnosis: str | None = None
    admitting_diagnosis: str | None = None
    diagnosis_codes: str | None = None
    npi: str | None = None
    ccn: str | None = None
    facility_canonical_id: str | None = None
    facility_name: str | None = None


class EventTypeRules(BaseModel):
    """Rules for mapping source event codes to canonical event types."""

    source_field: str
    mappings: dict[str, str]
    conditional_mappings: list[dict[str, str]] = []
    admit_flag_expression: str | None = None
    discharge_flag_expression: str | None = None


class PairedEventConfig(BaseModel):
    """Configuration for one side of a paired event (admit or discharge)."""

    event_ts: str
    event_type: str


class PairedEvents(BaseModel):
    """Paired event configuration for claims sources."""

    admit: PairedEventConfig
    discharge: PairedEventConfig


class PatientClassRules(BaseModel):
    """Rules for deriving patient class from source fields (e.g., bill type codes)."""

    conditions: list[dict[str, str]]


class AuthStatusMap(BaseModel):
    """Maps source auth status codes to standardized values."""

    source_field: str
    mappings: dict[str, str]


class FiltersConfig(BaseModel):
    """Filter configuration for excluding records during ingest."""

    exclude: str | None = None


class SourceConfig(BaseModel):
    """Complete source configuration combining all sub-configs."""

    name: str
    type: Literal["adt", "claims", "auth"]
    source: SourceDefinition
    field_mappings: FieldMappings
    event_type_rules: EventTypeRules
    paired_events: PairedEvents | None = None
    patient_class_rules: PatientClassRules | None = None
    auth_status_map: AuthStatusMap | None = None
    filters: FiltersConfig | None = None

    @model_validator(mode="after")
    def validate_source_type_requirements(self) -> SourceConfig:
        """Validate that claims sources have paired_events and auth sources have auth_status_map."""
        if self.type == "claims" and self.paired_events is None:
            raise ValueError("Claims sources must have paired_events defined")
        if self.type == "auth" and self.auth_status_map is None:
            raise ValueError("Auth sources must have auth_status_map defined")
        return self
