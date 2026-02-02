"""Tests for PipelineStage ABC and PipelineContext."""

from __future__ import annotations

import pytest

from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineStage


class TestPipelineContext:
    """Tests for PipelineContext dataclass."""

    def test_construction_with_required_fields(self) -> None:
        ctx = PipelineContext(
            run_id="run_20260201_120000",
            config={},
            mode="full",
        )
        assert ctx.run_id == "run_20260201_120000"
        assert ctx.config == {}
        assert ctx.mode == "full"

    def test_mode_incremental(self) -> None:
        ctx = PipelineContext(
            run_id="run_1",
            config={"key": "value"},
            mode="incremental",
        )
        assert ctx.mode == "incremental"
        assert ctx.config == {"key": "value"}

    def test_metrics_collector_default_none(self) -> None:
        ctx = PipelineContext(
            run_id="run_1",
            config={},
            mode="full",
        )
        assert ctx.metrics_collector is None

    def test_metrics_collector_provided(self) -> None:
        collector: list[dict[str, object]] = []
        ctx = PipelineContext(
            run_id="run_1",
            config={},
            mode="full",
            metrics_collector=collector,
        )
        assert ctx.metrics_collector is collector


class TestPipelineStage:
    """Tests for PipelineStage ABC."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            PipelineStage()  # type: ignore[abstract]

    def test_dummy_stage_implementation(self) -> None:
        class PassthroughStage(PipelineStage):
            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        stage = PassthroughStage()
        batch = EventBatch(batch_id="b1", events=[])
        ctx = PipelineContext(run_id="run_1", config={}, mode="full")
        result = stage.run(batch, ctx)
        assert result is batch

    def test_stage_must_implement_run(self) -> None:
        class IncompleteStage(PipelineStage):
            pass

        with pytest.raises(TypeError):
            IncompleteStage()  # type: ignore[abstract]
