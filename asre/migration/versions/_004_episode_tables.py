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
    from asre.migration.ddl_types import DDLTypeMapper

    wt = getattr(adapter, "warehouse_type", "postgres")
    m = DDLTypeMapper(wt)

    t = m.text()
    b = m.boolean()
    r = m.real()
    i = m.integer()
    pk = m.primary_key("episode_id")

    cols = [
        pk,
        f"patient_key {t} NOT NULL",
        f"episode_type {t} NOT NULL",
        f"episode_status {t} NOT NULL",
        f"episode_start_ts {t}",
        f"episode_end_ts {t}",
        f"total_los_days {r}",
        f"encounter_ids {t}",
        f"encounter_count {i}",
        f"facility_count {i}",
        f"facility_sequence {t}",
        f"includes_readmission {b}",
        f"includes_post_acute {b}",
        f"is_acute {b}",
        f"principal_diagnosis {t}",
        f"diagnosis_codes {t}",
        f"confidence_score {r}",
        f"created_at {t}",
        f"updated_at {t}",
    ]

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_episodes ({col_str})"
    )
