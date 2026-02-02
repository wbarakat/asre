"""Episode dataclass — the episode of care output schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class Episode:
    """An episode of care matching the asre_episodes schema.

    Fields align with SPEC §3.4 (asre_episodes).
    """

    # Required fields
    episode_id: str
    patient_key: str
    episode_type: str
    episode_status: str
    episode_start_ts: datetime
    encounter_ids: list[str]
    encounter_count: int
    facility_count: int
    facility_sequence: list[str]
    is_acute: bool
    confidence_score: float
    created_at: datetime
    updated_at: datetime

    # Optional fields (nullable in spec)
    episode_end_ts: datetime | None = None
    total_los_days: float | None = None
    includes_readmission: bool | None = None
    includes_post_acute: bool | None = None
    principal_diagnosis: str | None = None
    diagnosis_codes: list[dict[str, Any]] | None = None
