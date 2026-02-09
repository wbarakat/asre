"""Migration infrastructure for ASRE schema management."""

from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

from asre.ingest.base import IngestAdapter


class MigrationScript(Protocol):
    """Protocol for migration script modules."""

    def upgrade(self, adapter: IngestAdapter) -> None: ...

    @property
    def description(self) -> str: ...


@dataclass
class MigrationInfo:
    """Metadata about a discovered migration."""

    version: int
    description: str
    module_name: str


@dataclass
class MigrationResult:
    """Result of running migrations."""

    applied: int
    current_version: int


class Migrator:
    """Manages database schema migrations.

    Checks asre_metadata for schema_version, discovers migration scripts
    in asre/migration/versions/ ordered by filename prefix, and runs
    pending migrations.
    """

    _VERSIONS_DIR = os.path.join(os.path.dirname(__file__), "versions")

    def __init__(self, adapter: IngestAdapter) -> None:
        self._adapter = adapter

    def get_schema_version(self) -> int:
        """Get current schema version from asre_metadata.

        Creates the asre_metadata table if it doesn't exist.
        Returns 0 if no schema_version key found.
        """
        try:
            rows = self._adapter.read_source(
                "asre_metadata",
                "SELECT value FROM asre_metadata WHERE key = 'schema_version'",
            )
        except Exception:
            # Table doesn't exist — create it
            self._create_metadata_table()
            return 0

        if not rows:
            return 0
        return int(rows[0]["value"])

    def set_schema_version(self, version: int) -> None:
        """Set the schema version in asre_metadata via warehouse-appropriate upsert."""
        wt = getattr(self._adapter, "warehouse_type", "postgres")
        if wt == "redshift":
            self._adapter.execute_ddl(
                "DELETE FROM asre_metadata WHERE key = 'schema_version'"
            )
            self._adapter.execute_ddl(
                f"INSERT INTO asre_metadata (key, value) VALUES ('schema_version', '{version}')"
            )
        elif wt in ("snowflake", "bigquery"):
            self._adapter.execute_ddl(
                "MERGE INTO asre_metadata AS target "
                f"USING (SELECT 'schema_version' AS key, '{version}' AS value) AS source "
                "ON target.key = source.key "
                "WHEN MATCHED THEN UPDATE SET value = source.value "
                "WHEN NOT MATCHED THEN INSERT (key, value) VALUES (source.key, source.value)"
            )
        else:
            # Postgres (default)
            self._adapter.execute_ddl(
                "INSERT INTO asre_metadata (key, value) "
                f"VALUES ('schema_version', '{version}') "
                "ON CONFLICT (key) DO UPDATE SET value = "
                f"'{version}'"
            )

    def discover_migrations(self) -> list[MigrationInfo]:
        """Discover migration scripts in versions/ directory, ordered by version."""
        migrations: list[MigrationInfo] = []

        if not os.path.isdir(self._VERSIONS_DIR):
            return migrations

        pattern = re.compile(r"^_?(\d+)_(.+)\.py$")
        for filename in sorted(os.listdir(self._VERSIONS_DIR)):
            match = pattern.match(filename)
            if match:
                version = int(match.group(1))
                desc = match.group(2).replace("_", " ")
                module_name = f"asre.migration.versions.{filename[:-3]}"
                migrations.append(
                    MigrationInfo(
                        version=version,
                        description=desc,
                        module_name=module_name,
                    )
                )

        migrations.sort(key=lambda m: m.version)
        return migrations

    def run(self) -> MigrationResult:
        """Run all pending migrations.

        Returns MigrationResult with count of applied migrations
        and current schema version.
        """
        current_version = self.get_schema_version()
        migrations = self.discover_migrations()
        applied = 0

        for migration in migrations:
            if migration.version <= current_version:
                continue

            module = importlib.import_module(migration.module_name)
            module.upgrade(self._adapter)
            current_version = migration.version
            self.set_schema_version(current_version)
            applied += 1

        return MigrationResult(applied=applied, current_version=current_version)

    def rollback(self, target_version: int = 0) -> MigrationResult:
        """Rollback migrations down to target_version.

        Iterates migrations in reverse order, calling downgrade() on each
        migration whose version is > target_version.

        Args:
            target_version: Version to rollback to. Defaults to 0 (all migrations).

        Returns:
            MigrationResult with count of rolled-back migrations and current version.
        """
        current_version = self.get_schema_version()
        if current_version <= target_version:
            return MigrationResult(applied=0, current_version=current_version)

        migrations = self.discover_migrations()
        rolled_back = 0

        for migration in reversed(migrations):
            if migration.version <= target_version:
                continue
            if migration.version > current_version:
                continue

            module = importlib.import_module(migration.module_name)
            if hasattr(module, "downgrade"):
                module.downgrade(self._adapter)
                rolled_back += 1

            current_version = migration.version - 1
            if current_version > 0:
                self.set_schema_version(current_version)
            else:
                # Drop metadata table is handled by migration 001's downgrade
                try:
                    self._adapter.execute_ddl(
                        "DELETE FROM asre_metadata WHERE key = 'schema_version'"
                    )
                except Exception:
                    pass

        return MigrationResult(applied=rolled_back, current_version=target_version)

    def _create_metadata_table(self) -> None:
        """Create the asre_metadata table."""
        self._adapter.execute_ddl(
            "CREATE TABLE IF NOT EXISTS asre_metadata ("
            "key TEXT PRIMARY KEY, "
            "value TEXT NOT NULL"
            ")"
        )
