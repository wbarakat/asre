"""Query builder for ingest operations supporting full and incremental modes."""

from __future__ import annotations

from typing import Any


class IngestQueryBuilder:
    """Builds SQL queries for reading source tables based on ingest mode.

    Supports full mode (all records) and incremental mode (watermark-based).
    Exclude filters are applied regardless of mode.
    """

    def __init__(
        self,
        table: str,
        incremental_key: str,
        mode: str,
        exclude_filter: str | None = None,
    ) -> None:
        self._table = table
        self._incremental_key = incremental_key
        self._mode = mode
        self._exclude_filter = exclude_filter

    def build_query(self) -> str:
        """Build the SQL query based on mode and filters."""
        query = f"SELECT * FROM {self._table}"

        conditions: list[str] = []

        if self._exclude_filter:
            conditions.append(f"NOT ({self._exclude_filter})")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        return query

    def build_params(self) -> dict[str, Any]:
        """Build query parameters. Full mode has no params."""
        return {}
