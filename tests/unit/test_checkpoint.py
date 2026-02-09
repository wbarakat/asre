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

        mgr = CheckpointManager(adapter)
        mgr.save_checkpoint(
            run_id="run_20250101_120000",
            stage_name="ingest",
            stage_index=0,
        )

        # Verify upsert was called
        adapter.execute_ddl.assert_called_once()
        sql = adapter.execute_ddl.call_args[0][0]
        assert "asre_checkpoints" in sql
        assert "run_20250101_120000" in sql
        assert "ingest" in sql

    def test_checkpoint_contains_run_id_and_stage(self) -> None:
        """Checkpoint state includes: run_id, last_completed_stage, stage_index."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []

        mgr = CheckpointManager(adapter)
        mgr.save_checkpoint(
            run_id="run_20250101_120000",
            stage_name="stitch",
            stage_index=3,
        )

        sql = adapter.execute_ddl.call_args[0][0]
        assert "run_20250101_120000" in sql
        assert "stitch" in sql
        assert "3" in sql

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

        mgr = CheckpointManager(adapter)
        mgr.mark_completed(
            "run_20250101_120000",
            stage_name="episode_quality",
            stage_index=11,
        )

        sql = adapter.execute_ddl.call_args[0][0]
        assert "completed" in sql
        assert "episode_quality" in sql
        assert "11" in sql

    def test_checkpoint_status_failed_on_error(self) -> None:
        """When a stage fails, checkpoint status should be 'failed'."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.read_source.return_value = []

        mgr = CheckpointManager(adapter)
        mgr.mark_failed(
            run_id="run_20250101_120000",
            stage_name="dedup",
            stage_index=4,
            error="Stage dedup failed",
        )

        sql = adapter.execute_ddl.call_args[0][0]
        assert "failed" in sql
        assert "dedup" in sql
        assert "Stage dedup failed" in sql

    def test_save_checkpoint_uses_upsert_for_postgres(self) -> None:
        """save_checkpoint should upsert by run_id for Postgres."""
        from asre.pipeline.checkpoint import CheckpointManager

        adapter = MagicMock()
        adapter.warehouse_type = "postgres"

        mgr = CheckpointManager(adapter)
        mgr.save_checkpoint(
            run_id="run_20260101_000000",
            stage_name="ingest",
            stage_index=0,
        )

        adapter.execute_ddl.assert_called_once()
        sql = adapter.execute_ddl.call_args[0][0]
        assert "ON CONFLICT (run_id)" in sql


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
        config: dict[str, Any] = {"adapter": adapter}
        runner = PipelineRunner(config=config, mode="full")
        return runner

    def test_runner_saves_checkpoint_after_each_stage(self) -> None:
        """PipelineRunner should save a checkpoint after each stage completes."""
        adapter = MagicMock()
        adapter.read_source.return_value = []

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
            c for c in adapter.execute_ddl.call_args_list
            if "asre_checkpoints" in c[0][0]
        ]
        assert len(checkpoint_writes) >= 9

    def test_runner_resumes_from_checkpoint(self) -> None:
        """PipelineRunner should replay all stages when resuming for correctness."""
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

        # All stages should be replayed for correctness
        assert stages["ingest"].called
        assert stages["canonicalize"].called
        assert stages["facility_normalize"].called
        assert stages["stitch"].called
        assert stages["dedup"].called
        assert stages["reconcile"].called
        assert stages["score"].called
        assert stages["materialize"].called
        assert stages["quality_check"].called

    def test_full_mode_runs_cleanup_before_stages(self) -> None:
        """Full mode should clear derived tables before running stages."""
        adapter = MagicMock()
        adapter.read_source.return_value = []

        runner = self._make_runner_with_adapter(adapter)
        runner._stages = {"ingest": DummyStage("ingest")}

        runner.run()

        cleanup_calls = [
            c for c in adapter.execute_ddl.call_args_list
            if "DELETE FROM admission_events_unified" in c[0][0]
        ]
        assert cleanup_calls

    def test_failed_stage_records_checkpoint_with_failure(self) -> None:
        """When a stage fails, the checkpoint should record the failure."""
        adapter = MagicMock()
        adapter.read_source.return_value = []

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
            c for c in adapter.execute_ddl.call_args_list
            if "asre_checkpoints" in c[0][0]
            and "failed" in c[0][0]
        ]
        assert len(failed_writes) == 1
        assert "Stage dedup failed" in failed_writes[0][0][0]

    def test_resume_nonexistent_run_raises_error(self) -> None:
        """Resuming a run_id that doesn't exist should raise a clear error."""
        adapter = MagicMock()
        adapter.read_source.return_value = []

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
