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
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_facility_registry")
        adapter.execute_ddl("DROP TABLE IF EXISTS asre_canonical_events")
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
        latest_version = max(
            (m.version for m in migrator.discover_migrations()),
            default=0,
        )
        result = migrator.run()

        assert result.applied == latest_version
        assert result.current_version == latest_version

    def test_asre_metadata_table_created(self, pg_adapter: PostgresAdapter) -> None:
        """After migration, asre_metadata table exists with schema_version."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        latest_version = max(
            (m.version for m in migrator.discover_migrations()),
            default=0,
        )
        migrator.run()

        # Verify table exists by reading from it
        rows = pg_adapter.read_source(
            "asre_metadata",
            "SELECT key, value FROM asre_metadata WHERE key = 'schema_version'",
        )
        assert len(rows) == 1
        assert rows[0]["key"] == "schema_version"
        assert rows[0]["value"] == str(latest_version)

    def test_run_is_idempotent(self, pg_adapter: PostgresAdapter) -> None:
        """Running migrator twice doesn't error or re-apply."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        latest_version = max(
            (m.version for m in migrator.discover_migrations()),
            default=0,
        )
        result1 = migrator.run()
        result2 = migrator.run()

        assert result1.applied == latest_version
        assert result2.applied == 0
        assert result2.current_version == latest_version

    def test_schema_version_check(self, pg_adapter: PostgresAdapter) -> None:
        """get_schema_version returns correct value after migration."""
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        migrator = Migrator(pg_adapter)
        latest_version = max(
            (m.version for m in migrator.discover_migrations()),
            default=0,
        )
        migrator.run()

        version = migrator.get_schema_version()
        assert version == latest_version

    def test_auto_migration_on_fresh_database(self, pg_adapter: PostgresAdapter) -> None:
        """Auto-migration creates all tables from scratch on fresh DB."""
        # Drop everything to simulate a fresh install
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_episodes")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_facility_registry")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_canonical_events")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_quality_metrics")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_run_metrics")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_audit_log")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_encounters_detail")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS admission_events_unified")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_checkpoints")
        pg_adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")

        from asre.cli.main import _run_auto_migration

        _run_auto_migration(pg_adapter)

        # Verify key tables exist by querying them
        rows = pg_adapter.read_source(
            "asre_metadata",
            "SELECT key, value FROM asre_metadata WHERE key = 'schema_version'",
        )
        assert len(rows) == 1
        version = int(rows[0]["value"])
        assert version > 0

        # Verify output tables exist
        for table in [
            "admission_events_unified",
            "asre_encounters_detail",
            "asre_audit_log",
            "asre_run_metrics",
            "asre_quality_metrics",
            "asre_canonical_events",
            "asre_facility_registry",
        ]:
            result = pg_adapter.read_source(
                table,
                f"SELECT 1 FROM {table} LIMIT 0",
            )
            # Should not raise -- table exists
            assert isinstance(result, list)

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
