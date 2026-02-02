"""Tests for stage checkpointing (US-070).

Tests that intermediate results are persisted after each stage,
checkpoint state is stored in asre_metadata, and failed runs
can be resumed from the last completed stage.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage


class DummyStage(PipelineStage):
    """A test stage that records calls."""

    def __init__(self, name: str = "dummy") -> None:
        self.name = name
        self.called = False
        from asre.observability.metrics import StageMetrics

        self.metrics: Any = StageMetrics(name, "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        self.called = True
        return batch


class FailingStage(PipelineStage):
    """A stage that raises an error."""

    def __init__(self, name: str = "failing") -> None:
        self.name = name
        from asre.observability.metrics import StageMetrics

        self.metrics: Any = StageMetrics(name, "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        raise RuntimeError(f"Stage {self.name} failed")


class TestCheckpointState:
    """Tests for checkpoint creation and storage."""

    def test_checkpoint_created_after_each_stage(self) -> None:
        """After each stage completes, a checkpoint should be recorded."""
        from asre.pipeline.checkpoint import CheckpointManager

        # Use mock adapter for storage
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        mgr = CheckpointManager(adapter)
        mgr.save_checkpoint(
            run_id="run_20250101_120000",
            stage_name="ingest",
            stage_index=0,
        )

        # Verify write was called
        adapter.write_records.assert_called()
        call_args = adapter.write_records.call_args
        assert call_args[0][0] == "asre_checkpoints"
        records = call_args[0][1]
        assert len(records) == 1
        assert records[0]["run_id"] == "run_20250101_120000"
        assert records[0]["last_completed_stage"] == "ingest"
        assert records[0]["stage_index"] == 0

    def test_checkpoint_contains_run_id_and_stage(self) -> None:
        """Checkpoint state includes: run_id, last_completed_stage, stage_index."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        mgr = CheckpointManager(adapter)
        mgr.save_checkpoint(
            run_id="run_20250101_120000",
            stage_name="stitch",
            stage_index=3,
        )

        call_args = adapter.write_records.call_args
        record = call_args[0][1][0]
        assert "run_id" in record
        assert "last_completed_stage" in record
        assert "stage_index" in record
        assert record["stage_index"] == 3

    def test_load_checkpoint_returns_state(self) -> None:
        """Loading checkpoint for a run_id returns the last saved state."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = [
            {
                "run_id": "run_20250101_120000",
                "last_completed_stage": "dedup",
                "stage_index": 4,
                "status": "in_progress",
            }
        ]

        mgr = CheckpointManager(adapter)
        cp = mgr.load_checkpoint("run_20250101_120000")
        assert cp is not None
        assert cp["run_id"] == "run_20250101_120000"
        assert cp["last_completed_stage"] == "dedup"
        assert cp["stage_index"] == 4

    def test_load_checkpoint_returns_none_for_unknown_run(self) -> None:
        """Loading checkpoint for a non-existent run_id returns None."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []

        mgr = CheckpointManager(adapter)
        cp = mgr.load_checkpoint("run_nonexistent")
        assert cp is None

    def test_checkpoint_status_completed_after_full_run(self) -> None:
        """After all stages complete, checkpoint status should be 'completed'."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        mgr = CheckpointManager(adapter)
        mgr.mark_completed("run_20250101_120000")

        call_args = adapter.write_records.call_args
        record = call_args[0][1][0]
        assert record["status"] == "completed"

    def test_checkpoint_status_failed_on_error(self) -> None:
        """When a stage fails, checkpoint status should be 'failed'."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        mgr = CheckpointManager(adapter)
        mgr.mark_failed(
            run_id="run_20250101_120000",
            stage_name="dedup",
            stage_index=4,
            error="Stage dedup failed",
        )

        call_args = adapter.write_records.call_args
        record = call_args[0][1][0]
        assert record["status"] == "failed"
        assert record["last_completed_stage"] == "dedup"
        assert record["error"] == "Stage dedup failed"


class TestCheckpointManagerTable:
    """Tests for checkpoint table creation."""

    def test_ensure_table_creates_checkpoints_table(self) -> None:
        """CheckpointManager should create asre_checkpoints table if not exists."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []

        mgr = CheckpointManager(adapter)
        mgr.ensure_table()

        adapter.execute_ddl.assert_called_once()
        ddl = adapter.execute_ddl.call_args[0][0]
        assert "asre_checkpoints" in ddl
        assert "CREATE TABLE IF NOT EXISTS" in ddl


class TestPipelineRunnerCheckpointing:
    """Tests that PipelineRunner uses checkpointing."""

    def _make_runner_with_adapter(
        self, adapter: Any = None
    ) -> PipelineRunner:
        if adapter is None:
            adapter = MagicMock()
            adapter.read_source.return_value = []
            adapter.write_records.return_value = 1
        config: dict[str, Any] = {"adapter": adapter}
        runner = PipelineRunner(config=config, mode="full")
        return runner

    def test_runner_saves_checkpoint_after_each_stage(self) -> None:
        """PipelineRunner should save a checkpoint after each stage completes."""
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        runner = self._make_runner_with_adapter(adapter)
        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, PipelineStage] = {
            name: DummyStage(name) for name in stage_names
        }
        runner._stages = stages
        runner.run()

        # Should have written checkpoints (at least 9 stage checkpoints + 1 completion)
        checkpoint_writes = [
            c for c in adapter.write_records.call_args_list
            if c[0][0] == "asre_checkpoints"
        ]
        assert len(checkpoint_writes) >= 9

    def test_runner_resumes_from_checkpoint(self) -> None:
        """PipelineRunner should skip completed stages when resuming."""
        adapter = MagicMock()
        # Return a checkpoint indicating stitch (index 3) was last completed
        adapter.read_source.return_value = [
            {
                "run_id": "run_20250101_120000",
                "last_completed_stage": "stitch",
                "stage_index": 3,
                "status": "in_progress",
            }
        ]
        adapter.write_records.return_value = 1

        config: dict[str, Any] = {"adapter": adapter}
        runner = PipelineRunner(config=config, mode="full")
        runner.run_id = "run_20250101_120000"

        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, DummyStage] = {
            name: DummyStage(name) for name in stage_names
        }
        runner._stages = dict(stages)

        runner.run(resume_run_id="run_20250101_120000")

        # Stages 0-3 (ingest through stitch) should NOT have been called
        assert not stages["ingest"].called
        assert not stages["canonicalize"].called
        assert not stages["facility_normalize"].called
        assert not stages["stitch"].called

        # Stages 4+ (dedup onward) SHOULD have been called
        assert stages["dedup"].called
        assert stages["reconcile"].called
        assert stages["score"].called
        assert stages["materialize"].called
        assert stages["quality_check"].called

    def test_failed_stage_records_checkpoint_with_failure(self) -> None:
        """When a stage fails, the checkpoint should record the failure."""
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        runner = self._make_runner_with_adapter(adapter)

        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, PipelineStage] = {}
        for name in stage_names:
            if name == "dedup":
                stages[name] = FailingStage(name)
            else:
                stages[name] = DummyStage(name)

        runner._stages = stages

        with pytest.raises(RuntimeError, match="Stage dedup failed"):
            runner.run()

        # Should have a failed checkpoint write
        failed_writes = [
            c for c in adapter.write_records.call_args_list
            if c[0][0] == "asre_checkpoints"
            and len(c[0][1]) > 0
            and c[0][1][0].get("status") == "failed"
        ]
        assert len(failed_writes) == 1
        assert failed_writes[0][0][1][0]["error"] == "Stage dedup failed"

    def test_resume_nonexistent_run_raises_error(self) -> None:
        """Resuming a run_id that doesn't exist should raise a clear error."""
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        runner = self._make_runner_with_adapter(adapter)
        runner._stages = {
            name: DummyStage(name) for name in [
                "ingest", "canonicalize", "facility_normalize",
                "stitch", "dedup", "reconcile", "score",
                "materialize", "quality_check",
            ]
        }

        with pytest.raises(ValueError, match="not found"):
            runner.run(resume_run_id="run_nonexistent")

    def test_resume_completed_run_raises_error(self) -> None:
        """Resuming an already-completed run should raise an error."""
        adapter = MagicMock()
        adapter.read_source.return_value = [
            {
                "run_id": "run_20250101_120000",
                "last_completed_stage": "quality_check",
                "stage_index": 8,
                "status": "completed",
            }
        ]
        adapter.write_records.return_value = 1

        runner = self._make_runner_with_adapter(adapter)
        runner._stages = {
            name: DummyStage(name) for name in [
                "ingest", "canonicalize", "facility_normalize",
                "stitch", "dedup", "reconcile", "score",
                "materialize", "quality_check",
            ]
        }

        with pytest.raises(ValueError, match="already completed"):
            runner.run(resume_run_id="run_20250101_120000")
