"""004: Create episode tables for ASRE pipeline (US-095).

Creates the asre_episodes table for episode-level data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asre.ingest.base import IngestAdapter

description = "episode tables"


def upgrade(adapter: IngestAdapter) -> None:
    """Create the asre_episodes table."""
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS asre_episodes ("
        "episode_id TEXT PRIMARY KEY, "
        "patient_key TEXT NOT NULL, "
        "episode_type TEXT NOT NULL, "
        "episode_status TEXT NOT NULL, "
        "episode_start_ts TEXT, "
        "episode_end_ts TEXT, "
        "total_los_days REAL, "
        "encounter_ids TEXT, "
        "encounter_count INTEGER, "
        "facility_count INTEGER, "
        "facility_sequence TEXT, "
        "includes_readmission BOOLEAN, "
        "includes_post_acute BOOLEAN, "
        "is_acute BOOLEAN, "
        "principal_diagnosis TEXT, "
        "diagnosis_codes TEXT, "
        "confidence_score REAL, "
        "created_at TEXT, "
        "updated_at TEXT"
        ")"
    )
