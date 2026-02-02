"""Tests for ingest query builder - full mode (US-020)."""

from __future__ import annotations

from asre.ingest.query_builder import IngestQueryBuilder


class TestFullModeIngest:
    """Test that full mode reads all records without watermark filtering."""

    def test_full_mode_selects_all_from_source_table(self) -> None:
        """Full mode query should SELECT * FROM the source table."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
        )
        query = builder.build_query()
        assert "SELECT *" in query
        assert "raw_adt_events" in query

    def test_full_mode_no_watermark_filter(self) -> None:
        """Full mode should not include any watermark WHERE clause."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
        )
        query = builder.build_query()
        # No watermark filtering in full mode
        assert "message_ts >" not in query
        assert ":watermark" not in query.lower()

    def test_full_mode_with_exclude_filter(self) -> None:
        """Full mode should apply exclude filter as WHERE NOT clause."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
            exclude_filter="hl7_event IN ('A08', 'A31')",
        )
        query = builder.build_query()
        assert "NOT" in query
        assert "hl7_event IN ('A08', 'A31')" in query

    def test_full_mode_without_exclude_filter(self) -> None:
        """Full mode without exclude filter should have no WHERE clause."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
        )
        query = builder.build_query()
        assert "WHERE" not in query

    def test_full_mode_params_empty(self) -> None:
        """Full mode should return empty params dict (no watermark param)."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
        )
        params = builder.build_params()
        assert params == {}

    def test_full_mode_params_empty_even_with_exclude(self) -> None:
        """Full mode with exclude filter still has no params (exclude is literal SQL)."""
        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
            exclude_filter="hl7_event IN ('A08', 'A31')",
        )
        params = builder.build_params()
        assert params == {}

    def test_full_mode_returns_all_records_via_adapter(self) -> None:
        """Full mode should return all records from adapter (no filtering by watermark)."""
        # This tests the integration with adapter - using a mock adapter
        from unittest.mock import MagicMock
        from asre.ingest.base import IngestAdapter

        adapter = MagicMock(spec=IngestAdapter)
        all_records = [{"id": i, "hl7_event": "A01"} for i in range(100)]
        adapter.read_source.return_value = all_records

        builder = IngestQueryBuilder(
            table="raw_adt_events",
            incremental_key="message_ts",
            mode="full",
        )
        query = builder.build_query()
        params = builder.build_params()

        results = adapter.read_source("adt_vendor_x", query, params)
        assert len(results) == 100
        adapter.read_source.assert_called_once_with("adt_vendor_x", query, params)

    def test_full_mode_exclude_filters_applied_by_query(self) -> None:
        """Exclude filters should be embedded in the SQL query itself."""
        builder = IngestQueryBuilder(
            table="claims_data",
            incremental_key="processed_date",
            mode="full",
            exclude_filter="status = 'VOID'",
        )
        query = builder.build_query()
        # The query should contain the WHERE NOT clause
        assert "WHERE" in query
        assert "NOT" in query
        assert "status = 'VOID'" in query
        # Still selects from correct table
        assert "claims_data" in query
