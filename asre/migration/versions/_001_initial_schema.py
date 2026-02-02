"""001: Initial schema — creates asre_metadata and watermark tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asre.ingest.base import IngestAdapter

description = "initial schema"


def upgrade(adapter: IngestAdapter) -> None:
    """Create the asre_metadata table for key-value storage.

    This table is used for:
    - schema_version tracking (migration state)
    - watermark storage (per-source incremental processing state)
    """
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS asre_metadata ("
        "key TEXT PRIMARY KEY, "
        "value TEXT NOT NULL"
        ")"
    )
