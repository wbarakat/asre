"""Timestamp parsing utilities for canonicalization.

Ensures event_ts values are timezone-aware and normalized to UTC when no
timezone is provided by the source.
"""

from __future__ import annotations

from datetime import datetime, date, timezone
from typing import Any


def parse_event_ts(value: Any, *, default_tz: timezone = timezone.utc) -> datetime:
    """Parse event_ts into a timezone-aware datetime.

    - Naive datetimes are assumed to be in default_tz (UTC).
    - Date-only strings are treated as midnight in default_tz.
    - ISO strings with 'Z' are treated as UTC.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=default_tz)
        return value

    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=default_tz)

    raw = str(value).strip()
    if not raw:
        raise ValueError("event_ts is empty or null")

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=default_tz)
    return dt
