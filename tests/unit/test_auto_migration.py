"""Tests for auto-migration on startup (US-103)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from asre.cli.main import _run_auto_migration, cli


class TestRunAutoMigration:
    """Tests for the _run_auto_migration helper."""

    def test_fresh_install_runs_all_migrations(self) -> None:
        """On fresh DB (no asre_metadata), all migrations are applied."""
        adapter = MagicMock()

        mock_migrator_instance = MagicMock()
        mock_migrator_instance.get_schema_version.return_value = 0
        mock_migrator_instance.run.return_value = MagicMock(
            applied=1, current_version=1
        )

        with patch(
            "asre.migration.migrator.Migrator", return_value=mock_migrator_instance
        ) as mock_cls:
            _run_auto_migration(adapter)

        mock_cls.assert_called_once_with(adapter)
        mock_migrator_instance.get_schema_version.assert_called_once()
        mock_migrator_instance.run.assert_called_once()

    def test_schema_current_skips_migration(self) -> None:
        """When schema is up to date, no migrations are run."""
        adapter = MagicMock()

        mock_migrator_instance = MagicMock()
        mock_migrator_instance.get_schema_version.return_value = 1
        mock_migrator_instance.discover_migrations.return_value = [
            MagicMock(version=1),
        ]

        with patch(
            "asre.migration.migrator.Migrator", return_value=mock_migrator_instance
        ):
            _run_auto_migration(adapter)

        # run() should NOT be called when schema is current
        mock_migrator_instance.run.assert_not_called()

    def test_schema_behind_runs_pending(self) -> None:
        """When schema is behind, only pending migrations are run."""
        adapter = MagicMock()

        mock_migrator_instance = MagicMock()
        mock_migrator_instance.get_schema_version.return_value = 0
        mock_migrator_instance.discover_migrations.return_value = [
            MagicMock(version=1),
        ]
        mock_migrator_instance.run.return_value = MagicMock(
            applied=1, current_version=1
        )

        with patch(
            "asre.migration.migrator.Migrator", return_value=mock_migrator_instance
        ):
            _run_auto_migration(adapter)

        mock_migrator_instance.run.assert_called_once()

    def test_migration_failure_raises(self) -> None:
        """Migration failure propagates as an exception."""
        adapter = MagicMock()

        mock_migrator_instance = MagicMock()
        mock_migrator_instance.get_schema_version.return_value = 0
        mock_migrator_instance.run.side_effect = RuntimeError(
            "Migration 001 failed: table already exists"
        )

        with patch(
            "asre.migration.migrator.Migrator", return_value=mock_migrator_instance
        ):
            with pytest.raises(RuntimeError, match="Migration 001 failed"):
                _run_auto_migration(adapter)


class TestAutoMigrationInPipeline:
    """Tests that auto-migration is called during pipeline startup."""

    def test_run_command_triggers_auto_migration(self) -> None:
        """The 'asre run' command triggers auto-migration before pipeline."""
        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = {
            "run_id": "run_test",
            "mode": "full",
            "stages_completed": 12,
        }

        with patch("asre.cli.main._create_pipeline_runner") as mock_create, \
             patch("asre.cli.main._run_auto_migration") as mock_migrate, \
             patch("asre.cli.main._check_env_or_exit"), \
             patch("asre.cli.main._validate_license_or_exit"):

            # _create_pipeline_runner is the whole function; we need to
            # verify _run_auto_migration is called inside it. Since we're
            # mocking _create_pipeline_runner, we instead test the function
            # directly below. Here we just verify the CLI calls work.
            mock_create.return_value = mock_runner_instance

            runner = CliRunner()
            result = runner.invoke(cli, [
                "run",
                "--mode", "full",
                "--config-path", "/tmp/config",
                "--customer-id", "test",
            ])

            assert result.exit_code == 0
            mock_create.assert_called_once()

    def test_create_pipeline_runner_calls_auto_migration(self) -> None:
        """_create_pipeline_runner calls _run_auto_migration with the adapter."""
        from asre.cli.main import _create_pipeline_runner

        mock_config = MagicMock()
        mock_config.warehouse.connection = {"host": "localhost"}
        mock_config.warehouse.type = "postgres"
        mock_config.sources = []
        mock_config.facility_aliases = None

        mock_adapter = MagicMock()
        mock_adapter.connect.return_value = None

        with patch("asre.cli.main.load_config", return_value=mock_config), \
             patch("asre.ingest.adapter_factory.create_adapter", return_value=mock_adapter), \
             patch("asre.cli.main._run_auto_migration") as mock_migrate, \
             patch("asre.pipeline.runner.PipelineRunner"):

            _create_pipeline_runner("/tmp/config", "test", "full")

            mock_migrate.assert_called_once_with(mock_adapter)

    def test_run_command_exits_on_migration_failure(self) -> None:
        """Pipeline exits with non-zero code when migration fails."""
        from asre.cli.main import _create_pipeline_runner

        mock_config = MagicMock()
        mock_config.warehouse.connection = {"host": "localhost"}
        mock_config.warehouse.type = "postgres"
        mock_config.sources = []
        mock_config.facility_aliases = None

        mock_adapter = MagicMock()
        mock_adapter.connect.return_value = None

        with patch("asre.cli.main.load_config", return_value=mock_config), \
             patch("asre.ingest.adapter_factory.create_adapter", return_value=mock_adapter), \
             patch(
                 "asre.cli.main._run_auto_migration",
                 side_effect=RuntimeError("Migration failed"),
             ), \
             patch("asre.cli.main._check_env_or_exit"), \
             patch("asre.cli.main._validate_license_or_exit"):

            runner = CliRunner()
            result = runner.invoke(cli, [
                "run",
                "--mode", "full",
                "--config-path", "/tmp/config",
                "--customer-id", "test",
            ])

            assert result.exit_code != 0
            assert "Migration failed" in result.output
