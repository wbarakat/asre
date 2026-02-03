"""QualityCheckStage - pipeline stage for quality metric evaluation (US-085).

Computes quality metrics from scored encounters, evaluates thresholds,
fires webhook alerts if metrics breach thresholds, and writes metric
records to the asre_quality_metrics table.  Updates the watermark
after successful completion.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.quality.alerter import Alerter
from asre.quality.metrics import QualityMetricComputer

logger = logging.getLogger(__name__)

QUALITY_METRICS_TABLE = "asre_quality_metrics"


class QualityCheckStage(PipelineStage):
    """Pipeline stage that computes, evaluates, and persists quality metrics.

    Orchestrates:
    1. Metric computation via QualityMetricComputer
    2. Threshold evaluation (warn / fail / pass)
    3. Webhook alerting via Alerter
    4. Writing metric records to asre_quality_metrics
    5. Updating the watermark after success
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("quality_check", "")
        self.computed_metrics: dict[str, float] = {}
        self.metric_statuses: dict[str, str] = {}

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the quality check stage.

        When dry_run=True in context.config, computes metrics and evaluates
        thresholds but skips DB writes and watermark updates.
        """
        self.metrics = StageMetrics("quality_check", context.run_id)

        with self.metrics:
            encounters: list[Any] = context.config.get("scored_encounters", [])
            stage_metrics: list[dict[str, Any]] = context.config.get(
                "stage_metrics", []
            )
            encounters_created: int = context.config.get("encounters_created", 0)
            encounters_updated: int = context.config.get("encounters_updated", 0)
            dry_run: bool = context.config.get("dry_run", False)

            self.metrics.records_in = len(encounters)

            # 1. Compute metrics
            computer = QualityMetricComputer()
            self.computed_metrics = computer.compute(
                encounters=encounters,
                stage_metrics=stage_metrics,
                events_ingested=self._count_events_ingested(stage_metrics),
                encounters_created=encounters_created,
                encounters_updated=encounters_updated,
            )

            # 2. Evaluate thresholds
            alerting_cfg = self._get_alerting_config(context.config)
            thresholds: dict[str, float] = alerting_cfg.get("thresholds", {})
            self.metric_statuses = computer.evaluate_thresholds(
                self.computed_metrics, thresholds
            )

            if dry_run:
                logger.info(
                    "Dry-run mode: computed %d quality metrics "
                    "(skipping DB writes and watermark update). "
                    "Metrics: %s",
                    len(self.computed_metrics),
                    self.computed_metrics,
                )
                self.metrics.records_out = len(self.computed_metrics)
                return batch

            # 3. Fire alerts
            webhook_urls: list[str] = alerting_cfg.get("webhook_urls", [])
            alerter = Alerter(webhook_urls)
            alerter.fire(
                run_id=context.run_id,
                metrics=self.computed_metrics,
                statuses=self.metric_statuses,
                thresholds=thresholds,
            )

            # 4. Write metric records to DB
            records = computer.to_records(
                self.computed_metrics,
                context.run_id,
                statuses=self.metric_statuses,
            )
            adapter = context.config.get("adapter")
            if adapter is not None:
                self._ensure_table(adapter)
                adapter.write_records(QUALITY_METRICS_TABLE, records)

            # 5. Update watermark
            if adapter is not None:
                now = datetime.now(tz=timezone.utc).isoformat()
                adapter.set_watermark("quality_check", now)

            self.metrics.records_out = len(self.computed_metrics)

        return batch

    @staticmethod
    def _get_alerting_config(config: dict[str, Any]) -> dict[str, Any]:
        """Extract alerting config as a plain dict."""
        alerting = config.get("alerting", {})
        if hasattr(alerting, "model_dump"):
            # Pydantic model
            result: dict[str, Any] = alerting.model_dump()
            return result
        if isinstance(alerting, dict):
            return alerting
        return {}

    @staticmethod
    def _count_events_ingested(stage_metrics: list[dict[str, Any]]) -> int:
        """Sum records_in from ingest stage metrics."""
        for m in stage_metrics:
            if m.get("stage_name") == "ingest":
                return int(m.get("records_in", 0))
        # Fallback: sum all records_in
        total = 0
        for m in stage_metrics:
            total += int(m.get("records_in", 0))
        return total

    @staticmethod
    def _ensure_table(adapter: Any) -> None:
        """Create asre_quality_metrics table if it does not exist."""
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {QUALITY_METRICS_TABLE} ("
            "run_id TEXT NOT NULL, "
            "metric_name TEXT NOT NULL, "
            "metric_value REAL, "
            "warn_threshold REAL, "
            "fail_threshold REAL, "
            "status TEXT, "
            "computed_at TEXT, "
            "PRIMARY KEY (run_id, metric_name)"
            ")"
        )
        adapter.execute_ddl(ddl)
