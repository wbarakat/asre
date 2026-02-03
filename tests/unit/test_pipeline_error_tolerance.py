"""Tests for pipeline-level error tolerance (US-077).

The pipeline should tolerate individual event failures up to a configurable
threshold. If failed_event_rate exceeds the threshold, the pipeline halts.
Below threshold, the pipeline continues with failures tracked in metrics.
"""

from __future__ import annotations

from typing import Any

import pytest

from asre.pipeline.error_tolerance import (
    ErrorToleranceChecker,
    FailedEventRateExceededError,
)


class TestErrorToleranceChecker:
    """Tests for ErrorToleranceChecker."""

    def test_compute_failed_event_rate(self) -> None:
        """failed_event_rate = failed_events / total_events."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        rate = checker.compute_rate(failed=2, total=100)
        assert rate == pytest.approx(0.02)

    def test_compute_rate_zero_total(self) -> None:
        """Zero total events should produce rate 0.0 (no division by zero)."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        rate = checker.compute_rate(failed=0, total=0)
        assert rate == 0.0

    def test_below_threshold_continues(self) -> None:
        """2% failure rate with 5% threshold: pipeline continues."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        # Should not raise
        checker.check(failed=2, total=100)

    def test_above_threshold_halts(self) -> None:
        """10% failure rate with 5% threshold: pipeline halts."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        with pytest.raises(FailedEventRateExceededError) as exc_info:
            checker.check(failed=10, total=100)
        assert exc_info.value.rate == pytest.approx(0.10)
        assert exc_info.value.threshold == 0.05

    def test_exact_threshold_halts(self) -> None:
        """Exactly at threshold should halt (>= semantics)."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        with pytest.raises(FailedEventRateExceededError):
            checker.check(failed=5, total=100)

    def test_just_below_threshold_continues(self) -> None:
        """Just below threshold should continue."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        # 4.9% < 5%
        checker.check(failed=49, total=1000)

    def test_all_events_failed(self) -> None:
        """100% failure rate should halt."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        with pytest.raises(FailedEventRateExceededError) as exc_info:
            checker.check(failed=100, total=100)
        assert exc_info.value.rate == pytest.approx(1.0)

    def test_error_includes_details(self) -> None:
        """FailedEventRateExceededError should include rate, threshold, counts."""
        checker = ErrorToleranceChecker(fail_threshold=0.05)
        with pytest.raises(FailedEventRateExceededError) as exc_info:
            checker.check(failed=10, total=100)
        err = exc_info.value
        assert err.rate == pytest.approx(0.10)
        assert err.threshold == 0.05
        assert err.failed == 10
        assert err.total == 100

    def test_custom_threshold(self) -> None:
        """Custom threshold is respected."""
        checker = ErrorToleranceChecker(fail_threshold=0.20)
        # 15% < 20% - should not raise
        checker.check(failed=15, total=100)

    def test_custom_threshold_exceeded(self) -> None:
        """Custom threshold exceeded triggers halt."""
        checker = ErrorToleranceChecker(fail_threshold=0.20)
        with pytest.raises(FailedEventRateExceededError):
            checker.check(failed=25, total=100)


class TestPipelineRunnerErrorTolerance:
    """Tests for error tolerance integrated into PipelineRunner."""

    def _make_config(self, fail_threshold: float = 0.05) -> dict[str, Any]:
        """Create minimal pipeline config with alerting thresholds."""
        return {
            "sources": [],
            "alerting": {"thresholds": {"failed_event_rate_fail": fail_threshold}},
        }

    def test_pipeline_tracks_failed_events(self) -> None:
        """Pipeline should aggregate failed event counts across stages."""
        from collections import OrderedDict

        from asre.models.batch import EventBatch
        from asre.observability.metrics import StageMetrics
        from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage

        class FailingStage(PipelineStage):
            def __init__(self, records_in: int, records_out: int, errors: int) -> None:
                self.metrics = StageMetrics("test_stage", "")
                self._records_in = records_in
                self._records_out = records_out
                self._errors = errors

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics.records_in = self._records_in
                self.metrics.records_out = self._records_out
                self.metrics.errors = self._errors
                self.metrics.status = "success"
                return batch

        config = self._make_config(fail_threshold=0.05)
        runner = PipelineRunner(config=config, mode="full")
        # Replace stages with two custom stages that have errors
        runner._stages = OrderedDict(
            [
                ("stage_a", FailingStage(records_in=100, records_out=98, errors=2)),
            ]
        )

        result = runner.run()
        # Pipeline should complete (2% < 5%)
        assert result["run_id"].startswith("run_")

    def test_pipeline_halts_on_high_failure_rate(self) -> None:
        """Pipeline halts when failed_event_rate exceeds threshold."""
        from collections import OrderedDict

        from asre.models.batch import EventBatch
        from asre.observability.metrics import StageMetrics
        from asre.pipeline.error_tolerance import FailedEventRateExceededError
        from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage

        class HighFailStage(PipelineStage):
            def __init__(self) -> None:
                self.metrics = StageMetrics("test_stage", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics.records_in = 100
                self.metrics.records_out = 90
                self.metrics.errors = 10
                self.metrics.status = "success"
                return batch

        config = self._make_config(fail_threshold=0.05)
        runner = PipelineRunner(config=config, mode="full")
        runner._stages = OrderedDict(
            [
                ("stage_a", HighFailStage()),
            ]
        )

        with pytest.raises(FailedEventRateExceededError):
            runner.run()

    def test_pipeline_continues_below_threshold(self) -> None:
        """Pipeline continues when failure rate is below threshold."""
        from collections import OrderedDict

        from asre.models.batch import EventBatch
        from asre.observability.metrics import StageMetrics
        from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage

        class LowFailStage(PipelineStage):
            def __init__(self, name: str) -> None:
                self.metrics = StageMetrics(name, "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics.records_in = 100
                self.metrics.records_out = 99
                self.metrics.errors = 1
                self.metrics.status = "success"
                return batch

        config = self._make_config(fail_threshold=0.05)
        runner = PipelineRunner(config=config, mode="full")
        runner._stages = OrderedDict(
            [
                ("stage_a", LowFailStage("stage_a")),
                ("stage_b", LowFailStage("stage_b")),
            ]
        )

        result = runner.run()
        # 2 errors / 200 total = 1% < 5%
        assert result["run_id"].startswith("run_")

    def test_pipeline_halts_cumulative_failures(self) -> None:
        """Pipeline halts when cumulative failures across stages exceed threshold."""
        from collections import OrderedDict

        from asre.models.batch import EventBatch
        from asre.observability.metrics import StageMetrics
        from asre.pipeline.error_tolerance import FailedEventRateExceededError
        from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage

        class ModerateFailStage(PipelineStage):
            def __init__(self, name: str, errors: int) -> None:
                self.metrics = StageMetrics(name, "")
                self._errors = errors

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics.records_in = 100
                self.metrics.records_out = 100 - self._errors
                self.metrics.errors = self._errors
                self.metrics.status = "success"
                return batch

        config = self._make_config(fail_threshold=0.05)
        runner = PipelineRunner(config=config, mode="full")
        runner._stages = OrderedDict(
            [
                ("stage_a", ModerateFailStage("stage_a", errors=3)),
                ("stage_b", ModerateFailStage("stage_b", errors=8)),
            ]
        )

        with pytest.raises(FailedEventRateExceededError):
            runner.run()
