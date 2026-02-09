"""Adapter factory for warehouse-specific adapters."""

from __future__ import annotations

from typing import Any

from asre.ingest.base import IngestAdapter


def create_adapter(warehouse_type: str, connection: dict[str, Any]) -> IngestAdapter:
    """Create an ingest adapter based on warehouse type."""
    wtype = warehouse_type.lower()
    if wtype == "postgres":
        from asre.ingest.postgres import PostgresAdapter

        return PostgresAdapter(connection)
    if wtype == "snowflake":
        from asre.ingest.snowflake import SnowflakeAdapter

        return SnowflakeAdapter(connection)
    if wtype == "bigquery":
        from asre.ingest.bigquery import BigQueryAdapter

        return BigQueryAdapter(connection)
    if wtype == "redshift":
        from asre.ingest.redshift import RedshiftAdapter

        return RedshiftAdapter(connection)

    raise ValueError(f"Unsupported warehouse type: {warehouse_type}")
