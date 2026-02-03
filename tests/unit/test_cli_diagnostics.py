"""Tests for ASRE CLI diagnostic commands (US-078)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from asre.cli.main import cli


class TestStatusCommand:
    """Tests for 'asre status' command."""

    def test_status_command_exists(self) -> None:
        """status command appears in help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "status" in result.output

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_status_shows_last_run(self, mock_get_adapter: MagicMock) -> None:
        """status shows last run status and summary."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        # Return a checkpoint row for the last run
        adapter.read_source.side_effect = [
            # First call: asre_checkpoints query for latest run
            [
                {
                    "run_id": "run_20250101_120000",
                    "last_completed_stage": "quality_check",
                    "stage_index": 8,
                    "status": "completed",
                    "error": None,
                    "updated_at": "2025-01-01T12:05:00",
                },
            ],
            # Second call: asre_run_metrics for that run
            [
                {
                    "run_id": "run_20250101_120000",
                    "stage_name": "ingest",
                    "records_in": 100,
                    "records_out": 95,
                    "errors": 5,
                    "status": "completed",
                },
                {
                    "run_id": "run_20250101_120000",
                    "stage_name": "canonicalize",
                    "records_in": 95,
                    "records_out": 90,
                    "errors": 0,
                    "status": "completed",
                },
            ],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "status",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "run_20250101_120000" in result.output
        assert "completed" in result.output

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_status_no_runs(self, mock_get_adapter: MagicMock) -> None:
        """status with no prior runs shows informative message."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "status",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "none" in result.output.lower()


class TestInspectRunCommand:
    """Tests for 'asre inspect run <run_id>' command."""

    def test_inspect_command_group_exists(self) -> None:
        """inspect command group appears in help output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "inspect" in result.output

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_run_shows_stage_metrics(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """inspect run shows per-stage metrics for a run."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = [
            {
                "run_id": "run_20250101_120000",
                "stage_name": "ingest",
                "started_at": "2025-01-01T12:00:00",
                "completed_at": "2025-01-01T12:00:30",
                "records_in": 100,
                "records_out": 95,
                "errors": 5,
                "status": "completed",
            },
            {
                "run_id": "run_20250101_120000",
                "stage_name": "canonicalize",
                "started_at": "2025-01-01T12:00:30",
                "completed_at": "2025-01-01T12:01:00",
                "records_in": 95,
                "records_out": 90,
                "errors": 0,
                "status": "completed",
            },
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "run", "run_20250101_120000",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "ingest" in result.output
        assert "canonicalize" in result.output
        assert "100" in result.output  # records_in
        assert "95" in result.output   # records_out

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_run_not_found(self, mock_get_adapter: MagicMock) -> None:
        """inspect run with unknown run_id shows error."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "run", "run_nonexistent",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "not found" in result.output.lower()


class TestInspectEncounterCommand:
    """Tests for 'asre inspect encounter <id>' command."""

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_encounter_shows_details(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """inspect encounter shows encounter with all source events."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.side_effect = [
            # First call: admission_events_unified for the encounter
            [
                {
                    "encounter_id": "enc_001",
                    "patient_key": "PAT_001",
                    "encounter_type": "inpatient",
                    "status": "closed",
                    "admit_ts": "2025-01-01T10:00:00",
                    "discharge_ts": "2025-01-03T14:00:00",
                    "confidence_score": 0.85,
                    "facility_name": "General Hospital",
                },
            ],
            # Second call: asre_encounters_detail for its events
            [
                {
                    "encounter_id": "enc_001",
                    "event_id": "evt_001",
                    "event_type": "ADMIT",
                    "event_ts": "2025-01-01T10:00:00",
                    "source_system": "adt_vendor_x",
                    "role_in_encounter": "admit_anchor",
                },
                {
                    "encounter_id": "enc_001",
                    "event_id": "evt_002",
                    "event_type": "DISCHARGE",
                    "event_ts": "2025-01-03T14:00:00",
                    "source_system": "adt_vendor_x",
                    "role_in_encounter": "discharge_anchor",
                },
            ],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "encounter", "enc_001",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "enc_001" in result.output
        assert "PAT_001" in result.output
        assert "inpatient" in result.output
        assert "evt_001" in result.output
        assert "ADMIT" in result.output
        assert "admit_anchor" in result.output

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_encounter_not_found(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """inspect encounter with unknown ID shows error."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "encounter", "enc_nonexistent",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestInspectErrorsCommand:
    """Tests for 'asre inspect errors --last-run' command."""

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_errors_last_run(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """inspect errors --last-run shows failed events from last run."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.side_effect = [
            # First call: get latest run_id from checkpoints
            [{"run_id": "run_20250101_120000"}],
            # Second call: get audit log errors for that run
            [
                {
                    "log_id": "log_001",
                    "run_id": "run_20250101_120000",
                    "action": "ingest",
                    "entity_type": "event",
                    "entity_id": "src_001",
                    "detail": "Missing patient_key",
                },
                {
                    "log_id": "log_002",
                    "run_id": "run_20250101_120000",
                    "action": "canonicalize",
                    "entity_type": "event",
                    "entity_id": "src_002",
                    "detail": "Invalid event_ts",
                },
            ],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "errors", "--last-run",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "run_20250101_120000" in result.output
        assert "Missing patient_key" in result.output or "src_001" in result.output

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_errors_no_runs(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """inspect errors with no prior runs shows message."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "errors", "--last-run",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "no" in result.output.lower()

    @patch("asre.cli.main._get_diagnostic_adapter")
    def test_inspect_errors_no_errors(
        self, mock_get_adapter: MagicMock
    ) -> None:
        """inspect errors with no errors shows clean message."""
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter
        adapter.read_source.side_effect = [
            [{"run_id": "run_20250101_120000"}],
            [],  # no audit log errors
        ]

        runner = CliRunner()
        result = runner.invoke(cli, [
            "inspect", "errors", "--last-run",
            "--config-path", "/fake/path",
            "--customer-id", "test",
        ])
        assert result.exit_code == 0
        assert "no" in result.output.lower() or "clean" in result.output.lower()
