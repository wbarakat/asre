"""Encounter dataclass — the unified encounter output schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Encounter:
    """A unified encounter matching the admission_events_unified schema.

    Fields align with SPEC §3.4 (admission_events_unified).
    """

    # Required fields
    encounter_id: str
    patient_key: str
    encounter_type: str
    status: str
    admit_ts: datetime
    facility_canonical_id: str
    facility_name: str
    is_acute: bool
    source_event_ids: list[str]
    source_systems: list[str]
    has_adt: bool
    has_claims: bool
    has_auth: bool
    confidence_score: float
    confidence_flags: list[str]
    created_at: datetime
    updated_at: datetime
    asre_version: str

    # Optional fields (nullable in spec)
    discharge_ts: datetime | None = None
    los_hours: float | None = None
    admit_source_priority: str | None = None
    discharge_source_priority: str | None = None
    payer_id: str | None = None
    drg: str | None = None
    principal_diagnosis: str | None = None
    admitting_diagnosis: str | None = None
    diagnosis_codes: list[dict[str, Any]] | None = None
    is_readmission: bool | None = None
    readmission_days: int | None = None
    obs_to_ip_conversion: bool | None = None
    transfer_chain: list[str] | None = None
    episode_id: str | None = None
