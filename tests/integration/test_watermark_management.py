"""Integration tests for watermark management (US-024).

Tests that watermarks are stored in asre_metadata table, are per-source,
and can be set and retrieved correctly.

Requires a running PostgreSQL instance.
"""

from __future__ import annotations

import os
from collections.abc import Generator
from datetime import datetime, timezone

import pytest

from asre.ingest.postgres import PostgresAdapter


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
def metadata_table(pg_adapter: PostgresAdapter) -> Generator[str, None, None]:
    """Create the asre_metadata table, clean up after."""
    table_name = "asre_metadata"

    pg_adapter.execute_ddl(f"DROP TABLE IF EXISTS {table_name}")
    pg_adapter.execute_ddl(
        f"""
        CREATE TABLE {table_name} (
            key VARCHAR(255) PRIMARY KEY,
            value TEXT
        )
        """
    )

    yield table_name

    pg_adapter.execute_ddl(f"DROP TABLE IF EXISTS {table_name}")


class TestWatermarkManagement:
    """Integration tests: watermark persistence in asre_metadata table."""

    def test_get_watermark_returns_none_when_no_watermark_exists(
        self, pg_adapter: PostgresAdapter, metadata_table: str
    ) -> None:
        """First run: no watermark exists, get_watermark returns None."""
        result = pg_adapter.get_watermark("adt_vendor_x")
        assert result is None

    def test_set_and_get_watermark_roundtrip(
        self, pg_adapter: PostgresAdapter, metadata_table: str
    ) -> None:
        """Set a watermark, then retrieve it and verify the value matches."""
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        pg_adapter.set_watermark("adt_vendor_x", ts)

        result = pg_adapter.get_watermark("adt_vendor_x")
        assert result is not None
        assert result == ts

    def test_watermarks_are_per_source(
        self, pg_adapter: PostgresAdapter, metadata_table: str
    ) -> None:
        """Different sources have independent watermarks."""
        ts_adt = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        ts_claims = datetime(2026, 1, 20, 14, 0, 0, tzinfo=timezone.utc)
        ts_auth = datetime(2026, 1, 18, 8, 0, 0, tzinfo=timezone.utc)

        pg_adapter.set_watermark("adt_vendor_x", ts_adt)
        pg_adapter.set_watermark("claims_clearinghouse", ts_claims)
        pg_adapter.set_watermark("auth_portal", ts_auth)

        assert pg_adapter.get_watermark("adt_vendor_x") == ts_adt
        assert pg_adapter.get_watermark("claims_clearinghouse") == ts_claims
        assert pg_adapter.get_watermark("auth_portal") == ts_auth

    def test_set_watermark_updates_existing_value(
        self, pg_adapter: PostgresAdapter, metadata_table: str
    ) -> None:
        """Setting watermark for a source that already has one updates it (upsert)."""
        ts1 = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 20, 14, 0, 0, tzinfo=timezone.utc)

        pg_adapter.set_watermark("adt_vendor_x", ts1)
        assert pg_adapter.get_watermark("adt_vendor_x") == ts1

        pg_adapter.set_watermark("adt_vendor_x", ts2)
        assert pg_adapter.get_watermark("adt_vendor_x") == ts2

    def test_watermark_stored_in_asre_metadata_table(
        self, pg_adapter: PostgresAdapter, metadata_table: str
    ) -> None:
        """Verify watermark is physically stored in asre_metadata table with expected key format."""
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        pg_adapter.set_watermark("adt_vendor_x", ts)

        # Directly query the table to verify storage format
        rows = pg_adapter.read_source(
            "direct_check",
            "SELECT key, value FROM asre_metadata WHERE key = :key",
            {"key": "watermark_adt_vendor_x"},
        )
        assert len(rows) == 1
        assert rows[0]["key"] == "watermark_adt_vendor_x"
        assert rows[0]["value"] == ts.isoformat()
