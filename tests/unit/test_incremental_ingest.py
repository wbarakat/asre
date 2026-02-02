"""Tests for incremental mode ingest with lookback buffer (US-021)."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

from asre.ingest.query_builder import IngestQueryBuilder


class TestIncrementalModeQuery:
    """Test that incremental mode filters by watermark minus lookback buffer."""

    def test_incremental_mode_filters_by_incremental_key(self) -> None:
        """Incremental mode query should filter by incremental_key > watermark."""
        watermark = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="incremental",
            watermark=watermark,
            lookback_buffer_hours=24,
        )
        query = builder.build_query()
        assert "message_ts >" in query
        assert ":watermark" in query

    def test_incremental_mode_params_contain_watermark(self) -> None:
        """Incremental mode should return params with adjusted watermark value."""
        watermark = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="incremental",
            watermark=watermark,
            lookback_buffer_hours=24,
        )
        params = builder.build_params()
        assert "watermark" in params
        # Watermark should be adjusted back by lookback buffer (24 hours)
        expected = watermark - timedelta(hours=24)
        assert params["watermark"] == expected

    def test_incremental_mode_lookback_72h_for_claims(self) -> None:
        """Claims sources use 72h lookback buffer."""
        watermark = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table="claims_data",
            incremental_key="processed_date",
            mode="incremental",
            watermark=watermark,
            lookback_buffer_hours=72,
        )
        params = builder.build_params()
        expected = watermark - timedelta(hours=72)
        assert params["watermark"] == expected

    def test_incremental_mode_with_exclude_filter(self) -> None:
        """Incremental mode should combine watermark filter AND exclude filter."""
        watermark = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="incremental",
            watermark=watermark,
            lookback_buffer_hours=24,
            exclude_filter="hl7_event IN ('A08', 'A31')",
        )
        query = builder.build_query()
        assert "message_ts >" in query
        assert "NOT" in query
        assert "hl7_event IN ('A08', 'A31')" in query
        # Both conditions should be joined with AND
        assert "AND" in query

    def test_incremental_mode_no_watermark_behaves_like_full(self) -> None:
        """If no watermark exists (first run), incremental mode behaves like full mode."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="incremental",
            watermark=None,
            lookback_buffer_hours=24,
        )
        query = builder.build_query()
        # No watermark filtering when watermark is None
        assert "message_ts >" not in query
        assert ":watermark" not in query

    def test_incremental_mode_no_watermark_params_empty(self) -> None:
        """If no watermark exists, params should be empty (like full mode)."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="incremental",
            watermark=None,
            lookback_buffer_hours=24,
        )
        params = builder.build_params()
        assert params == {}

    def test_incremental_mode_no_watermark_with_exclude_still_applies(self) -> None:
        """Even without watermark, exclude filters still apply."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="incremental",
            watermark=None,
            lookback_buffer_hours=24,
            exclude_filter="hl7_event IN ('A08', 'A31')",
        )
        query = builder.build_query()
        assert "NOT" in query
        assert "hl7_event IN ('A08', 'A31')" in query
        # But no watermark filter
        assert "message_ts >" not in query


class TestLookbackBufferParsing:
    """Test the helper that resolves lookback buffer hours from config."""

    def test_resolve_adt_lookback(self) -> None:
        """ADT source type resolves to adt-specific lookback buffer."""
        from asre.ingest.query_builder import resolve_lookback_buffer_hours
        lookback_config = {
            "default": "24h",
            "adt": "24h",
            "claims": "72h",
            "auth": "24h",
        }
        assert resolve_lookback_buffer_hours(lookback_config, "adt") == 24

    def test_resolve_claims_lookback(self) -> None:
        """Claims source type resolves to claims-specific lookback buffer."""
        from asre.ingest.query_builder import resolve_lookback_buffer_hours
        lookback_config = {
            "default": "24h",
            "adt": "24h",
            "claims": "72h",
            "auth": "24h",
        }
        assert resolve_lookback_buffer_hours(lookback_config, "claims") == 72

    def test_resolve_auth_lookback(self) -> None:
        """Auth source type resolves to auth-specific lookback buffer."""
        from asre.ingest.query_builder import resolve_lookback_buffer_hours
        lookback_config = {
            "default": "24h",
            "adt": "24h",
            "claims": "72h",
            "auth": "48h",
        }
        assert resolve_lookback_buffer_hours(lookback_config, "auth") == 48

    def test_resolve_fallback_to_default(self) -> None:
        """Unknown source type falls back to default lookback buffer."""
        from asre.ingest.query_builder import resolve_lookback_buffer_hours
        lookback_config = {
            "default": "24h",
            "adt": "24h",
            "claims": "72h",
        }
        assert resolve_lookback_buffer_hours(lookback_config, "eligibility") == 24

    def test_resolve_hours_format(self) -> None:
        """Lookback buffer with 'h' suffix parses correctly."""
        from asre.ingest.query_builder import resolve_lookback_buffer_hours
        lookback_config = {"default": "48h"}
        assert resolve_lookback_buffer_hours(lookback_config, "adt") == 48

    def test_resolve_days_format(self) -> None:
        """Lookback buffer with 'd' suffix converts to hours."""
        from asre.ingest.query_builder import resolve_lookback_buffer_hours
        lookback_config = {"default": "3d"}
        assert resolve_lookback_buffer_hours(lookback_config, "adt") == 72


class TestFullModeUnchanged:
    """Verify full mode still works correctly with new watermark parameters."""

    def test_full_mode_ignores_watermark(self) -> None:
        """Full mode should ignore watermark even if provided."""
        watermark = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
            watermark=watermark,
            lookback_buffer_hours=24,
        )
        query = builder.build_query()
        assert "message_ts >" not in query
        assert ":watermark" not in query

    def test_full_mode_params_still_empty(self) -> None:
        """Full mode params remain empty even with watermark provided."""
        watermark = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
            watermark=watermark,
            lookback_buffer_hours=24,
        )
        params = builder.build_params()
        assert params == {}
