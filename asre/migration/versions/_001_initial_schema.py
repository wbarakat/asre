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
    from asre.migration.ddl_types import DDLTypeMapper

    wt = getattr(adapter, "warehouse_type", "postgres")
    m = DDLTypeMapper(wt)

    cols = [
        f"key {m.text()} {'NOT NULL' if wt == 'bigquery' else ''}",
        f"value {m.text()} NOT NULL",
    ]

    pk = m.primary_key("key")
    # For non-bigquery, use PRIMARY KEY constraint on the key column directly
    if wt != "bigquery":
        cols[0] = f"key {m.text()} PRIMARY KEY"
    else:
        cols[0] = f"key {m.text()} NOT NULL"

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_metadata ({col_str})"
    )
