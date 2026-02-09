"""Tests for QualityCheckStage (US-085).

Verifies that the quality check stage:
- Implements PipelineStage interface
- Computes metrics from scored encounters
- Evaluates thresholds
- Fires alerts when metrics breach thresholds
- Writes quality metric records to the database
- Updates watermark after successful completion
- Records stage metrics (records_in, records_out)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineStage


# ---------------------------------------------------------------------------
# Helpers: lightweight encounter stub
# ---------------------------------------------------------------------------

@dataclass
class _FakeEncounter:
    """Minimal encounter stub with fields used by QualityMetricComputer."""

    encounter_id: str = "enc_001"
    patient_key: str = "P001"
    confidence_score: float = 0.75
    confidence_flags: list[str] = field(default_factory=list)
    facility_canonical_id: str | None = "FAC_001"


def _make_context(
    run_id: str = "run_20240101_120000",
    *,
    alerting_config: dict[str, Any] | None = None,
    adapter: Any = None,
    stage_metrics: list[dict[str, Any]] | None = None,
    encounters: list[Any] | None = None,
    encounters_created: int = 0,
    encounters_updated: int = 0,
    block_on_statuses: list[str] | None = None,
) -> PipelineContext:
    """Build a PipelineContext with quality-check-relevant config."""
    config: dict[str, Any] = {}

    if alerting_config is not None:
        config["alerting"] = alerting_config
    else:
        config["alerting"] = {
            "webhook_urls": [],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.15,
            },
            "block_on_statuses": block_on_statuses or [],
        }

    if adapter is not None:
        config["adapter"] = adapter

    # Pipeline runner stores stage_metrics on the runner; quality check stage
    # needs access via context config.
    if stage_metrics is not None:
        config["stage_metrics"] = stage_metrics
    else:
        config["stage_metrics"] = []

    # Scored encounters from materialize stage
    if encounters is not None:
        config["scored_encounters"] = encounters
    else:
        config["scored_encounters"] = []

    config["encounters_created"] = encounters_created
    config["encounters_updated"] = encounters_updated

    return PipelineContext(
        run_id=run_id,
        config=config,
        mode="full",
    )


# ===================================================================
# Test: Import and interface
# ===================================================================

class TestQualityCheckStageImport:
    """Verify the stage is importable and implements PipelineStage."""

    def test_importable(self) -> None:
        from asre.quality.stage import QualityCheckStage  # noqa: F401

    def test_implements_pipeline_stage(self) -> None:
        from asre.quality.stage import QualityCheckStage

        assert issubclass(QualityCheckStage, PipelineStage)

    def test_instantiates(self) -> None:
        from asre.quality.stage import QualityCheckStage

        stage = QualityCheckStage()
        assert stage is not None

    def test_has_metrics_attribute(self) -> None:
        from asre.quality.stage import QualityCheckStage

        stage = QualityCheckStage()
        assert hasattr(stage, "metrics")


# ===================================================================
# Test: Metric computation
# ===================================================================

class TestQualityCheckStageComputeMetrics:
    """Verify the stage computes metrics from encounters."""

    def test_computes_metrics_from_encounters(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [
            _FakeEncounter(confidence_score=0.90, confidence_flags=["HAS_CLAIMS"]),
            _FakeEncounter(confidence_score=0.40, confidence_flags=["MISSING_DISCHARGE"]),
        ]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        # Stage should have computed_metrics available
        assert hasattr(stage, "computed_metrics")
        assert "avg_confidence_score" in stage.computed_metrics
        assert "missing_discharge_rate" in stage.computed_metrics

    def test_computes_correct_avg_score(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [
            _FakeEncounter(confidence_score=0.80),
            _FakeEncounter(confidence_score=0.60),
        ]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        assert stage.computed_metrics["avg_confidence_score"] == pytest.approx(0.70)

    def test_uses_stage_metrics_for_failed_event_rate(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter()]
        stage_metrics = [
            {"stage_name": "ingest", "records_in": 100, "records_out": 95, "errors": 5},
        ]
        ctx = _make_context(encounters=encounters, stage_metrics=stage_metrics)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        assert stage.computed_metrics["failed_event_rate"] == pytest.approx(0.05)


# ===================================================================
# Test: Threshold evaluation
# ===================================================================

class TestQualityCheckStageThresholds:
    """Verify the stage evaluates thresholds correctly."""

    def test_evaluates_thresholds(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [
            _FakeEncounter(confidence_score=0.90, confidence_flags=[]),
        ]
        alerting = {
            "webhook_urls": [],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.15,
            },
            "block_on_statuses": [],
        }
        ctx = _make_context(encounters=encounters, alerting_config=alerting)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        assert hasattr(stage, "metric_statuses")
        assert stage.metric_statuses["duplicate_rate"] == "pass"

    def test_detects_warn_status(self) -> None:
        from asre.quality.stage import QualityCheckStage

        # 1 out of 2 encounters has DUPLICATE_DETECTED => rate=0.50 which is > warn=0.05
        encounters = [
            _FakeEncounter(confidence_flags=["DUPLICATE_DETECTED"]),
            _FakeEncounter(confidence_flags=[]),
        ]
        alerting = {
            "webhook_urls": [],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.60,
            },
            "block_on_statuses": [],
        }
        ctx = _make_context(encounters=encounters, alerting_config=alerting)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        assert stage.metric_statuses["duplicate_rate"] == "warn"

    def test_detects_fail_status(self) -> None:
        from asre.quality.stage import QualityCheckStage

        # 1 out of 2 encounters has DUPLICATE_DETECTED => rate=0.50 which is > fail=0.15
        encounters = [
            _FakeEncounter(confidence_flags=["DUPLICATE_DETECTED"]),
            _FakeEncounter(confidence_flags=[]),
        ]
        alerting = {
            "webhook_urls": [],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.15,
            },
            "block_on_statuses": [],
        }
        ctx = _make_context(encounters=encounters, alerting_config=alerting)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        assert stage.metric_statuses["duplicate_rate"] == "fail"

    def test_quality_gate_raises_on_fail_status(self) -> None:
        from asre.quality.errors import QualityGateError
        from asre.quality.stage import QualityCheckStage

        encounters = [
            _FakeEncounter(confidence_flags=["DUPLICATE_DETECTED"]),
        ]
        alerting = {
            "webhook_urls": [],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.15,
            },
            "block_on_statuses": ["fail"],
        }
        adapter = MagicMock()
        adapter.write_records.return_value = 12
        ctx = _make_context(encounters=encounters, alerting_config=alerting, adapter=adapter)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        with pytest.raises(QualityGateError):
            stage.run(batch, ctx)

        adapter.write_records.assert_called_once()
        adapter.set_watermark.assert_not_called()


# ===================================================================
# Test: Alerting
# ===================================================================

class TestQualityCheckStageAlerting:
    """Verify the stage fires alerts when thresholds breached."""

    def test_fires_alerts_when_thresholds_breached(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [
            _FakeEncounter(confidence_flags=["DUPLICATE_DETECTED"]),
        ]
        alerting = {
            "webhook_urls": ["https://example.com/webhook"],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.15,
            },
            "block_on_statuses": [],
        }
        ctx = _make_context(encounters=encounters, alerting_config=alerting)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        with patch("asre.quality.stage.Alerter") as MockAlerter:
            mock_alerter_instance = MagicMock()
            MockAlerter.return_value = mock_alerter_instance
            mock_alerter_instance.fire.return_value = True

            stage.run(batch, ctx)

            MockAlerter.assert_called_once_with(["https://example.com/webhook"])
            mock_alerter_instance.fire.assert_called_once()

    def test_no_alerts_when_all_pass(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [
            _FakeEncounter(confidence_score=0.95, confidence_flags=[]),
        ]
        alerting = {
            "webhook_urls": ["https://example.com/webhook"],
            "thresholds": {
                "duplicate_rate_warn": 0.05,
                "duplicate_rate_fail": 0.15,
            },
            "block_on_statuses": [],
        }
        ctx = _make_context(encounters=encounters, alerting_config=alerting)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        with patch("asre.quality.stage.Alerter") as MockAlerter:
            mock_alerter_instance = MagicMock()
            MockAlerter.return_value = mock_alerter_instance
            mock_alerter_instance.fire.return_value = False

            stage.run(batch, ctx)

            # Alerter still called but fire returns false (no alerts needed)
            mock_alerter_instance.fire.assert_called_once()

    def test_no_alerter_when_no_webhook_urls(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter()]
        alerting_cfg: dict[str, Any] = {
            "webhook_urls": [],
            "thresholds": {},
            "block_on_statuses": [],
        }
        ctx = _make_context(encounters=encounters, alerting_config=alerting_cfg)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        # Should not raise even with empty webhook URLs
        stage.run(batch, ctx)


# ===================================================================
# Test: Writing quality metrics to DB
# ===================================================================

class TestQualityCheckStageWriteMetrics:
    """Verify the stage writes quality metric records to the database."""

    def test_writes_records_to_adapter(self) -> None:
        from asre.quality.stage import QualityCheckStage

        adapter = MagicMock()
        adapter.write_records.return_value = 12
        encounters = [
            _FakeEncounter(confidence_score=0.80),
        ]
        ctx = _make_context(encounters=encounters, adapter=adapter)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        # Should write to asre_quality_metrics table
        adapter.write_records.assert_called_once()
        call_args = adapter.write_records.call_args
        assert call_args[0][0] == "asre_quality_metrics"
        records = call_args[0][1]
        assert len(records) == 12  # 12 metrics
        assert all("run_id" in r for r in records)
        assert all("metric_name" in r for r in records)
        assert all("status" in r for r in records)

    def test_skips_write_when_no_adapter(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter()]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        # Should not raise without adapter
        stage.run(batch, ctx)

    def test_ensures_table_before_writing(self) -> None:
        from asre.quality.stage import QualityCheckStage

        adapter = MagicMock()
        adapter.write_records.return_value = 12
        encounters = [_FakeEncounter()]
        ctx = _make_context(encounters=encounters, adapter=adapter)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        assert adapter.execute_ddl.call_count >= 1
        ddl_arg = adapter.execute_ddl.call_args_list[0][0][0]
        assert "asre_quality_metrics" in ddl_arg
        assert "CREATE TABLE IF NOT EXISTS" in ddl_arg


# ===================================================================
# Test: Watermark update
# ===================================================================

class TestQualityCheckStageWatermark:
    """Verify the stage updates watermark after successful completion."""

    def test_updates_watermark_when_adapter_present(self) -> None:
        from asre.quality.stage import QualityCheckStage
        from datetime import datetime

        adapter = MagicMock()
        adapter.write_records.return_value = 12
        encounters = [_FakeEncounter()]
        ctx = _make_context(encounters=encounters, adapter=adapter)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        # Watermark should be set via adapter
        adapter.set_watermark.assert_called_once()
        args = adapter.set_watermark.call_args[0]
        assert args[0] == "quality_check"  # source_name
        assert isinstance(args[1], datetime)


# ===================================================================
# Test: Stage metrics
# ===================================================================

class TestQualityCheckStageMetrics:
    """Verify the stage records correct stage metrics."""

    def test_records_in_equals_encounter_count(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter(), _FakeEncounter()]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        metrics_dict = stage.metrics.to_dict()
        assert metrics_dict["records_in"] == 2

    def test_records_out_equals_metrics_written(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter()]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        metrics_dict = stage.metrics.to_dict()
        assert metrics_dict["records_out"] == 12  # 12 quality metrics computed

    def test_status_is_success(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter()]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, ctx)

        metrics_dict = stage.metrics.to_dict()
        assert metrics_dict["status"] == "success"

    def test_returns_batch_unchanged(self) -> None:
        from asre.quality.stage import QualityCheckStage

        encounters = [_FakeEncounter()]
        ctx = _make_context(encounters=encounters)
        stage = QualityCheckStage()
        batch = EventBatch(batch_id="test", events=[])

        result = stage.run(batch, ctx)

        assert result is batch
