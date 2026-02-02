"""Canonical event dataclass — the shared contract for all pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CanonicalEvent:
    """A single canonical event produced by the canonicalize stage.

    All pipeline stages consume and produce these events via EventBatch.
    Fields align with SPEC §3.2.
    """

    # Required fields
    event_id: str
    patient_key: str
    event_type: str
    event_ts: datetime
    source_system: str
    source_record_id: str
    facility_raw: str
    ingested_at: datetime
    batch_id: str

    # Optional fields (nullable in spec)
    facility_canonical_id: str | None = None
    admit_flag: bool | None = None
    discharge_flag: bool | None = None
    auth_flag: bool | None = None
    patient_class: str | None = None
    drg: str | None = None
    principal_diagnosis: str | None = None
    diagnosis_codes: list[dict[str, Any]] | None = None
    auth_status: str | None = None
    payer_id: str | None = None
    _raw_payload: dict[str, Any] | None = field(default=None, repr=False)
