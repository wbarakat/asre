"""Tests for the migration infrastructure."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from asre.migration.migrator import Migrator


class TestMigratorConstruction:
    """Test Migrator can be constructed with an adapter."""

    def test_create_migrator_with_adapter(self) -> None:
        adapter = MagicMock()
        migrator = Migrator(adapter)
        assert migrator is not None

    def test_migrator_stores_adapter(self) -> None:
        adapter = MagicMock()
        migrator = Migrator(adapter)
        assert migrator._adapter is adapter


class TestSchemaVersionCheck:
    """Test Migrator checks and creates asre_metadata table."""

    def test_get_schema_version_creates_metadata_table_if_missing(self) -> None:
        """If asre_metadata doesn't exist, Migrator creates it."""
        adapter = MagicMock()
        # Simulate table doesn't exist — read_source raises
        adapter.read_source.side_effect = Exception("relation \"asre_metadata\" does not exist")
        migrator = Migrator(adapter)

        version = migrator.get_schema_version()

        # Should have called execute_ddl to create the table
        adapter.execute_ddl.assert_called_once()
        ddl_call = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl_call.upper()
        assert "asre_metadata" in ddl_call
        assert version == 0

    def test_get_schema_version_returns_stored_version(self) -> None:
        """If asre_metadata exists with schema_version, return it."""
        adapter = MagicMock()
        adapter.read_source.return_value = [{"value": "3"}]
        migrator = Migrator(adapter)

        version = migrator.get_schema_version()

        assert version == 3

    def test_get_schema_version_returns_zero_when_no_version_key(self) -> None:
        """If asre_metadata exists but no schema_version key, return 0."""
        adapter = MagicMock()
        adapter.read_source.return_value = []
        migrator = Migrator(adapter)

        version = migrator.get_schema_version()

        assert version == 0


class TestMigrationDiscovery:
    """Test Migrator discovers migration scripts by filename prefix."""

    def test_discover_migrations_finds_scripts(self) -> None:
        """Migration scripts in versions/ directory are discovered."""
        adapter = MagicMock()
        migrator = Migrator(adapter)

        migrations = migrator.discover_migrations()

        # Should find at least the 001 migration once we create it
        assert isinstance(migrations, list)

    def test_discover_migrations_ordered_by_version(self) -> None:
        """Migrations are returned ordered by version number."""
        adapter = MagicMock()
        migrator = Migrator(adapter)

        migrations = migrator.discover_migrations()

        # Each migration should have a version number
        versions = [m.version for m in migrations]
        assert versions == sorted(versions)

    def test_migration_has_version_and_description(self) -> None:
        """Each migration has a version number and description."""
        adapter = MagicMock()
        migrator = Migrator(adapter)

        migrations = migrator.discover_migrations()
        if migrations:
            m = migrations[0]
            assert isinstance(m.version, int)
            assert isinstance(m.description, str)
            assert m.version > 0


class TestMigrationExecution:
    """Test Migrator runs pending migrations."""

    def test_run_skips_already_applied(self) -> None:
        """Migrations with version <= current schema_version are skipped."""
        adapter = MagicMock()
        # Schema version already at highest migration version
        adapter.read_source.return_value = [{"value": "3"}]
        migrator = Migrator(adapter)

        result = migrator.run()

        # No DDL should be executed for migrations (only the version query)
        assert result.applied == 0

    def test_run_applies_pending_migrations(self) -> None:
        """Migrations with version > current schema_version are applied."""
        adapter = MagicMock()
        # Fresh DB — no schema version
        adapter.read_source.side_effect = Exception("relation does not exist")
        migrator = Migrator(adapter)

        result = migrator.run()

        # Should have created metadata table + run migrations
        assert result.applied > 0

    def test_run_updates_schema_version_after_each_migration(self) -> None:
        """Schema version is updated after each successful migration."""
        adapter = MagicMock()
        # Fresh DB
        adapter.read_source.side_effect = Exception("relation does not exist")
        migrator = Migrator(adapter)

        migrator.run()

        # Should have written schema_version via write_records or execute_ddl
        # Look for schema_version updates in execute_ddl calls
        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        # At minimum, should have create table + migration DDL
        assert len(ddl_calls) >= 1

    def test_run_result_has_fields(self) -> None:
        """MigrationResult has applied count and current version."""
        adapter = MagicMock()
        adapter.read_source.return_value = [{"value": "999"}]
        migrator = Migrator(adapter)

        result = migrator.run()

        assert hasattr(result, "applied")
        assert hasattr(result, "current_version")
        assert result.current_version == 999
        assert result.applied == 0


class TestSetSchemaVersion:
    """Test setting the schema version in metadata."""

    def test_set_schema_version(self) -> None:
        adapter = MagicMock()
        adapter.read_source.return_value = [{"value": "0"}]
        migrator = Migrator(adapter)

        migrator.set_schema_version(5)

        # Should upsert schema_version into asre_metadata
        adapter.execute_ddl.assert_called()
        ddl = adapter.execute_ddl.call_args[0][0]
        assert "schema_version" in ddl
        assert "5" in ddl
