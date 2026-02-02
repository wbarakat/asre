"""Tests for US-071 - Resume support (--resume flag on asre run CLI).

Tests cover:
- CLI `asre run` command with --mode and --resume flags
- Resume logic with mock checkpoints
- Error handling: run_id not found, already completed
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from asre.cli.main import cli
from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage


class DummyStage(PipelineStage):
    """A test stage that records calls."""

    def __init__(self, name: str = "dummy") -> None:
        self.name = name
        self.called = False

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        self.called = True
        return batch


def _make_dummy_stages() -> dict[str, DummyStage]:
    """Create a full set of dummy stages."""
    return {
        name: DummyStage(name)
        for name in [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
    }


class TestRunCommandExists:
    """Tests for the `asre run` CLI command."""

    def test_run_command_in_help(self) -> None:
        """The 'run' command should appear in CLI help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "run" in result.output

    def test_run_accepts_mode_flag(self) -> None:
        """asre run --mode full should be accepted."""
        runner = CliRunner()
        with patch("asre.cli.main._create_pipeline_runner") as mock_create:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {
                "run_id": "run_20250101_120000",
                "mode": "full",
                "stages_completed": 9,
            }
            mock_create.return_value = mock_runner
            result = runner.invoke(cli, [
                "run",
                "--mode", "full",
                "--config-path", "/tmp/fake",
                "--customer-id", "test",
            ])
        assert result.exit_code == 0

    def test_run_accepts_resume_flag(self) -> None:
        """asre run --resume <run_id> should be accepted."""
        runner = CliRunner()
        with patch("asre.cli.main._create_pipeline_runner") as mock_create:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {
                "run_id": "run_20250101_120000",
                "mode": "full",
                "stages_completed": 9,
            }
            mock_create.return_value = mock_runner
            result = runner.invoke(cli, [
                "run",
                "--resume", "run_20250101_120000",
                "--config-path", "/tmp/fake",
                "--customer-id", "test",
            ])
        # Should call run with resume_run_id
        mock_runner.run.assert_called_once_with(
            resume_run_id="run_20250101_120000"
        )
        assert result.exit_code == 0

    def test_run_default_mode_is_incremental(self) -> None:
        """asre run without --mode should default to incremental."""
        runner = CliRunner()
        with patch("asre.cli.main._create_pipeline_runner") as mock_create:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {
                "run_id": "run_20250101_120000",
                "mode": "incremental",
                "stages_completed": 9,
            }
            mock_create.return_value = mock_runner
            result = runner.invoke(cli, [
                "run",
                "--config-path", "/tmp/fake",
                "--customer-id", "test",
            ])
        # Default mode should be incremental
        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs[1]["mode"] == "incremental" or call_kwargs[0][1] == "incremental"


class TestResumeLogicWithMockCheckpoints:
    """Tests for resume logic using PipelineRunner with mock checkpoints."""

    def test_resume_skips_completed_stages(self) -> None:
        """Resuming a run that completed through stage 4 should skip stages 0-4."""
        mock_adapter = MagicMock()
        # Checkpoint says stages 0-4 completed (through 'dedup', index 4)
        mock_adapter.read_source.return_value = [{
            "run_id": "run_20250101_120000",
            "last_completed_stage": "dedup",
            "stage_index": 4,
            "status": "failed",
            "error": "Stage reconcile failed",
            "updated_at": "2025-01-01T12:00:00+00:00",
        }]

        config: dict[str, Any] = {"adapter": mock_adapter}
        runner = PipelineRunner(config=config, mode="full")
        stages = _make_dummy_stages()
        runner._stages = stages  # type: ignore[assignment]

        runner.run(resume_run_id="run_20250101_120000")

        # Stages 0-4 should be skipped
        assert not stages["ingest"].called
        assert not stages["canonicalize"].called
        assert not stages["facility_normalize"].called
        assert not stages["stitch"].called
        assert not stages["dedup"].called

        # Stages 5-8 should run
        assert stages["reconcile"].called
        assert stages["score"].called
        assert stages["materialize"].called
        assert stages["quality_check"].called

    def test_resume_uses_original_run_id(self) -> None:
        """Resuming should use the original run_id, not generate a new one."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.return_value = [{
            "run_id": "run_20250101_120000",
            "last_completed_stage": "score",
            "stage_index": 6,
            "status": "failed",
            "error": "Stage materialize failed",
            "updated_at": "2025-01-01T12:00:00+00:00",
        }]

        config: dict[str, Any] = {"adapter": mock_adapter}
        runner = PipelineRunner(config=config, mode="full")
        stages = _make_dummy_stages()
        runner._stages = stages  # type: ignore[assignment]

        runner.run(resume_run_id="run_20250101_120000")

        assert runner.run_id == "run_20250101_120000"

    def test_resume_not_found_raises_error(self) -> None:
        """Resuming with unknown run_id should raise ValueError."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.return_value = []  # No checkpoint

        config: dict[str, Any] = {"adapter": mock_adapter}
        runner = PipelineRunner(config=config, mode="full")
        stages = _make_dummy_stages()
        runner._stages = stages  # type: ignore[assignment]

        with pytest.raises(ValueError, match="not found"):
            runner.run(resume_run_id="run_nonexistent")

    def test_resume_already_completed_raises_error(self) -> None:
        """Resuming a completed run should raise ValueError."""
        mock_adapter = MagicMock()
        mock_adapter.read_source.return_value = [{
            "run_id": "run_20250101_120000",
            "last_completed_stage": "quality_check",
            "stage_index": 8,
            "status": "completed",
            "error": None,
            "updated_at": "2025-01-01T12:00:00+00:00",
        }]

        config: dict[str, Any] = {"adapter": mock_adapter}
        runner = PipelineRunner(config=config, mode="full")
        stages = _make_dummy_stages()
        runner._stages = stages  # type: ignore[assignment]

        with pytest.raises(ValueError, match="already completed"):
            runner.run(resume_run_id="run_20250101_120000")

    def test_resume_no_adapter_raises_error(self) -> None:
        """Resuming without an adapter configured should raise ValueError."""
        config: dict[str, Any] = {}  # No adapter
        runner = PipelineRunner(config=config, mode="full")
        stages = _make_dummy_stages()
        runner._stages = stages  # type: ignore[assignment]

        with pytest.raises(ValueError, match="no adapter configured"):
            runner.run(resume_run_id="run_20250101_120000")


class TestRunCLIErrorHandling:
    """Tests for CLI error handling during resume."""

    def test_run_resume_not_found_shows_error(self) -> None:
        """CLI shows clear error when run_id not found."""
        runner = CliRunner()
        with patch("asre.cli.main._create_pipeline_runner") as mock_create:
            mock_runner = MagicMock()
            mock_runner.run.side_effect = ValueError(
                "Checkpoint for run 'run_nonexistent' not found"
            )
            mock_create.return_value = mock_runner
            result = runner.invoke(cli, [
                "run",
                "--resume", "run_nonexistent",
                "--config-path", "/tmp/fake",
                "--customer-id", "test",
            ])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()

    def test_run_resume_already_completed_shows_error(self) -> None:
        """CLI shows clear error when run already completed."""
        runner = CliRunner()
        with patch("asre.cli.main._create_pipeline_runner") as mock_create:
            mock_runner = MagicMock()
            mock_runner.run.side_effect = ValueError(
                "Run 'run_20250101_120000' already completed"
            )
            mock_create.return_value = mock_runner
            result = runner.invoke(cli, [
                "run",
                "--resume", "run_20250101_120000",
                "--config-path", "/tmp/fake",
                "--customer-id", "test",
            ])
        assert result.exit_code != 0
        assert "already completed" in result.output.lower()
