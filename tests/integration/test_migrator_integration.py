"""Integration tests for the migration infrastructure against PostgreSQL."""

from __future__ import annotations

import os
from typing import Any, Generator

import pytest

from asre.ingest.postgres import PostgresAdapter
from asre.migration.migrator import Migrator


def _pg_config() -> dict[str, Any]:
    return {
        "host": os.environ.get("ASRE_TEST_PG_HOST", "localhost"),
        "port": os.environ.get("ASRE_TEST_PG_PORT", "5432"),
        "database": os.environ.get("ASRE_TEST_PG_DATABASE", "asre_test"),
        "user": os.environ.get("ASRE_TEST_PG_USER", "postgres"),
        "password": os.environ.get("ASRE_TEST_PG_PASSWORD", "postgres"),
        "schema": "public",
    }


@pytest.fixture()
def pg_adapter() -> Generator[PostgresAdapter, None, None]:
    adapter = PostgresAdapter(_pg_config())
    try:
        adapter.connect()
    except ConnectionError:
        pytest.skip("PostgreSQL not available for integration tests")
    yield adapter
    # Clean up: drop all tables created by migrations
    try:
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_quality_metrics")
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_run_metrics")
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_audit_log")
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_encounters_detail")
        adapter.execute_ddl("DROP TABLE IF EXISTS admission_events_unified")
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")
    except Exception:
        pass
    adapter.disconnect()


class TestMigratorIntegration:
    """Integration tests running Migrator against real PostgreSQL."""

    def test_run_on_empty_database(self, pg_adapter: PostgresAdapter) -> None:
        """Running migrator on empty DB creates tables."""
        # Ensure clean state
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        result = migrator.run()

        assert result.applied == 2
        assert result.current_version == 3

    def test_asre_metadata_table_created(self, pg_adapter: PostgresAdapter) -> None:
        """After migration, asre_metadata table exists with schema_version."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        migrator.run()

        # Verify table exists by reading from it
        rows = pg_adapter.read_source(
            "asre_metadata",
            "SELECT key, value FROM asre_metadata WHERE key = 'schema_version'",
        )
        assert len(rows) == 1
        assert rows[0]["key"] == "schema_version"
        assert rows[0]["value"] == "4"

    def test_run_is_idempotent(self, pg_adapter: PostgresAdapter) -> None:
        """Running migrator twice doesn't error or re-apply."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        result1 = migrator.run()
        result2 = migrator.run()

        assert result1.applied == 3
        assert result2.applied == 0
        assert result2.current_version == 4

    def test_schema_version_check(self, pg_adapter: PostgresAdapter) -> None:
        """get_schema_version returns correct value after migration."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        migrator.run()

        version = migrator.get_schema_version()
        assert version == 3

    def test_watermark_works_after_migration(self, pg_adapter: PostgresAdapter) -> None:
        """Watermark management works on the migrated asre_metadata table."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        migrator.run()

        # Watermark uses the same asre_metadata table
        from datetime import datetime, timezone
        ts = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        pg_adapter.set_watermark("test_source", ts)
        result = pg_adapter.get_watermark("test_source")
        assert result == ts
