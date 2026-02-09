"""Tests for pipeline runner health state integration."""

from __future__ import annotations

from collections import OrderedDict

import pytest

from asre.models.batch import EventBatch
from asre.observability.health import PipelineHealthState
from asre.pipeline.runner import PipelineRunner, PipelineStage, PipelineContext


class _PassStage(PipelineStage):
    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        return batch


class _FailStage(PipelineStage):
    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        raise RuntimeError("boom")


class TestPipelineRunnerHealthState:
    def test_run_resets_health_state_to_ok(self) -> None:
        state = PipelineHealthState()
        state.mark_failed("previous failure")

        runner = PipelineRunner(config={"health_state": state}, mode="full")
        runner._stages = OrderedDict([("pass", _PassStage())])  # type: ignore[attr-defined]

        result = runner.run()

        assert state.is_healthy()
        assert result["stages_completed"] == 0

    def test_run_marks_health_failed_on_stage_error(self) -> None:
        state = PipelineHealthState()

        runner = PipelineRunner(config={"health_state": state}, mode="full")
        runner._stages = OrderedDict([("fail", _FailStage())])  # type: ignore[attr-defined]

        with pytest.raises(RuntimeError, match="boom"):
            runner.run()

        assert not state.is_healthy()
        assert state.error is not None
        assert "Stage fail failed" in state.error
