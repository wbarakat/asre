"""Tests for parse_event_ts normalization to timezone-aware datetimes."""

from __future__ import annotations

from datetime import datetime, date, timezone

import pytest

from asre.canonicalize.timestamp_parser import parse_event_ts


class TestParseEventTs:
    def test_parses_naive_iso_to_utc(self) -> None:
        dt = parse_event_ts("2024-01-15T10:30:00")
        assert dt == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_parses_date_only_to_midnight_utc(self) -> None:
        dt = parse_event_ts("2024-01-15")
        assert dt == datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)

    def test_parses_datetime_object_naive_to_utc(self) -> None:
        dt = parse_event_ts(datetime(2024, 1, 15, 10, 30, 0))
        assert dt == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_preserves_timezone_aware_datetime(self) -> None:
        aware = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        dt = parse_event_ts(aware)
        assert dt is aware

    def test_parses_z_suffix_to_utc(self) -> None:
        dt = parse_event_ts("2024-01-15T10:30:00Z")
        assert dt == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
