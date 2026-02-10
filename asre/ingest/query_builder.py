"""Query builder for ingest operations supporting full and incremental modes."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def resolve_lookback_buffer_hours(
    lookback_config: dict[str, str], source_type: str
) -> int:
    """Resolve lookback buffer hours from config for a given source type.

    Falls back to 'default' if source type is not configured.
    Supports 'h' (hours) and 'd' (days) suffixes.
    """
    raw = lookback_config.get(source_type, lookback_config["default"])
    if raw.endswith("d"):
        return int(raw[:-1]) * 24
    if raw.endswith("h"):
        return int(raw[:-1])
    return int(raw)


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
        watermark: datetime | None = None,
        lookback_buffer_hours: int = 24,
        order_by: list[str] | None = None,
    ) -> None:
        self._table = table
        self._incremental_key = incremental_key
        self._mode = mode
        self._exclude_filter = exclude_filter
        self._watermark = watermark
        self._lookback_buffer_hours = lookback_buffer_hours
        self._order_by = order_by or []

    def _should_apply_watermark(self) -> bool:
        """Check if watermark filtering should be applied."""
        return self._mode == "incremental" and self._watermark is not None

    def build_query(self) -> str:
        """Build the SQL query based on mode and filters."""
        query = f"SELECT * FROM {self._table}"  # nosec B608

        conditions: list[str] = []

        if self._should_apply_watermark():
            conditions.append(f"{self._incremental_key} > :watermark")

        if self._exclude_filter:
            conditions.append(f"NOT ({self._exclude_filter})")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if self._order_by:
            order_clause = ", ".join(self._order_by)
            query += f" ORDER BY {order_clause}"

        return query

    def build_params(self) -> dict[str, Any]:
        """Build query parameters."""
        if self._should_apply_watermark():
            if self._watermark is None:
                raise RuntimeError("Watermark must be set for incremental mode")
            adjusted = self._watermark - timedelta(hours=self._lookback_buffer_hours)
            return {"watermark": adjusted}
        return {}
