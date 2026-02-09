"""Integration tests for exclude filters (US-023).

Tests that filters.exclude expressions from source config are applied
as WHERE NOT clauses, excluding matching records from query results.

Requires a running PostgreSQL instance.
"""

from __future__ import annotations

import os
from collections.abc import Generator

import pytest

from asre.ingest.postgres import PostgresAdapter
from asre.ingest.query_builder import IngestQueryBuilder


def _pg_config() -> dict[str, str]:
    """Build Postgres config from env vars with sensible defaults for local dev."""
    return {
        "host": os.environ.get("ASRE_TEST_PG_HOST", "localhost"),
        "port": os.environ.get("ASRE_TEST_PG_PORT", "5432"),
        "database": os.environ.get("ASRE_TEST_PG_DATABASE", "asre_test"),
        "user": os.environ.get("ASRE_TEST_PG_USER", "postgres"),
        "password": os.environ.get("ASRE_TEST_PG_PASSWORD", "postgres"),
        "schema": os.environ.get("ASRE_TEST_PG_SCHEMA", "public"),
    }


@pytest.fixture
def pg_adapter() -> Generator[PostgresAdapter, None, None]:
    """Create a connected PostgresAdapter for integration tests."""
    adapter = PostgresAdapter(_pg_config())
    try:
        adapter.connect()
    except ConnectionError:
        pytest.skip("PostgreSQL not available for integration tests")
    yield adapter
    adapter.disconnect()


@pytest.fixture
def adt_table(pg_adapter: PostgresAdapter) -> Generator[str, None, None]:
    """Create and populate a test ADT events table, clean up after."""
    table_name = "test_raw_adt_events"

    # Create table
    pg_adapter.execute_ddl(f"DROP TABLE IF EXISTS {table_name}")
    pg_adapter.execute_ddl(
        f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            message_control_id VARCHAR(50),
            patient_mrn VARCHAR(50),
            hl7_event VARCHAR(10),
            message_ts TIMESTAMP,
            sending_facility VARCHAR(100)
        )
        """
    )

    # Insert test records: mix of A01 (admit), A03 (discharge), A08 (update), A31 (update person)
    records = [
        {"message_control_id": "MSG001", "patient_mrn": "PAT-001", "hl7_event": "A01", "message_ts": "2026-01-15 10:00:00", "sending_facility": "ST MARYS"},
        {"message_control_id": "MSG002", "patient_mrn": "PAT-001", "hl7_event": "A03", "message_ts": "2026-01-18 14:00:00", "sending_facility": "ST MARYS"},
        {"message_control_id": "MSG003", "patient_mrn": "PAT-002", "hl7_event": "A01", "message_ts": "2026-01-16 08:00:00", "sending_facility": "MEMORIAL"},
        {"message_control_id": "MSG004", "patient_mrn": "PAT-001", "hl7_event": "A08", "message_ts": "2026-01-15 12:00:00", "sending_facility": "ST MARYS"},
        {"message_control_id": "MSG005", "patient_mrn": "PAT-002", "hl7_event": "A31", "message_ts": "2026-01-16 09:00:00", "sending_facility": "MEMORIAL"},
        {"message_control_id": "MSG006", "patient_mrn": "PAT-003", "hl7_event": "A01", "message_ts": "2026-01-17 07:00:00", "sending_facility": "GOOD SAM"},
        {"message_control_id": "MSG007", "patient_mrn": "PAT-003", "hl7_event": "A08", "message_ts": "2026-01-17 10:00:00", "sending_facility": "GOOD SAM"},
    ]
    pg_adapter.write_records(table_name, records)

    yield table_name

    # Cleanup
    pg_adapter.execute_ddl(f"DROP TABLE IF EXISTS {table_name}")


class TestExcludeFilters:
    """Integration tests: exclude filters remove matching records from ingest results."""

    def test_exclude_filter_removes_a08_and_a31_events(
        self, pg_adapter: PostgresAdapter, adt_table: str
    ) -> None:
        """Records matching exclude filter (A08, A31) are not returned."""
        builder = IngestQueryBuilder(
            table=adt_table,
            incremental_key="message_ts",
            mode="full",
            exclude_filter="hl7_event IN ('A08', 'A31')",
        )
        query = builder.build_query()
        params = builder.build_params()

        results = pg_adapter.read_source("adt_vendor_x", query, params)

        # 7 total records - 3 excluded (2 A08 + 1 A31) = 4 remaining
        assert len(results) == 4
        hl7_events = {r["hl7_event"] for r in results}
        assert "A08" not in hl7_events
        assert "A31" not in hl7_events

    def test_exclude_filter_keeps_non_matching_events(
        self, pg_adapter: PostgresAdapter, adt_table: str
    ) -> None:
        """Records NOT matching exclude filter (A01, A03) are returned."""
        builder = IngestQueryBuilder(
            table=adt_table,
            incremental_key="message_ts",
            mode="full",
            exclude_filter="hl7_event IN ('A08', 'A31')",
        )
        query = builder.build_query()
        params = builder.build_params()

        results = pg_adapter.read_source("adt_vendor_x", query, params)

        hl7_events = {r["hl7_event"] for r in results}
        assert "A01" in hl7_events
        assert "A03" in hl7_events

    def test_no_exclude_filter_returns_all_records(
        self, pg_adapter: PostgresAdapter, adt_table: str
    ) -> None:
        """Without exclude filter, all 7 records are returned."""
        builder = IngestQueryBuilder(
            table=adt_table,
            incremental_key="message_ts",
            mode="full",
        )
        query = builder.build_query()
        params = builder.build_params()

        results = pg_adapter.read_source("adt_vendor_x", query, params)
        assert len(results) == 7

    def test_exclude_filter_with_single_event_type(
        self, pg_adapter: PostgresAdapter, adt_table: str
    ) -> None:
        """Exclude filter targeting a single event type works correctly."""
        builder = IngestQueryBuilder(
            table=adt_table,
            incremental_key="message_ts",
            mode="full",
            exclude_filter="hl7_event = 'A08'",
        )
        query = builder.build_query()
        params = builder.build_params()

        results = pg_adapter.read_source("adt_vendor_x", query, params)

        # 7 total - 2 A08 events = 5 remaining
        assert len(results) == 5
        hl7_events = {r["hl7_event"] for r in results}
        assert "A08" not in hl7_events
        # A31 should still be present since we only excluded A08
        assert "A31" in hl7_events

    def test_exclude_filter_applies_in_incremental_mode(
        self, pg_adapter: PostgresAdapter, adt_table: str
    ) -> None:
        """Exclude filters are applied in incremental mode too (combined with watermark)."""
        from datetime import datetime, timezone

        watermark = datetime(2026, 1, 16, 0, 0, 0, tzinfo=timezone.utc)
        builder = IngestQueryBuilder(
            table=adt_table,
            incremental_key="message_ts",
            mode="incremental",
            exclude_filter="hl7_event IN ('A08', 'A31')",
            watermark=watermark,
            lookback_buffer_hours=0,  # No lookback for precise testing
        )
        query = builder.build_query()
        params = builder.build_params()

        results = pg_adapter.read_source("adt_vendor_x", query, params)

        # After Jan 16 00:00: MSG002 (A03), MSG003 (A01), MSG005 (A31), MSG006 (A01), MSG007 (A08)
        # Excluding A08 and A31 leaves MSG002 (A03), MSG003 (A01), MSG006 (A01)
        assert len(results) == 3
        hl7_events = {r["hl7_event"] for r in results}
        assert "A08" not in hl7_events
        assert "A31" not in hl7_events
        assert "A01" in hl7_events
        assert "A03" in hl7_events

    def test_exclude_filter_with_no_matching_records(
        self, pg_adapter: PostgresAdapter, adt_table: str
    ) -> None:
        """Exclude filter that matches nothing returns all records."""
        builder = IngestQueryBuilder(
            table=adt_table,
            incremental_key="message_ts",
            mode="full",
            exclude_filter="hl7_event = 'A99'",
        )
        query = builder.build_query()
        params = builder.build_params()

        results = pg_adapter.read_source("adt_vendor_x", query, params)
        assert len(results) == 7
