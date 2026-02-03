"""Quality metric computation for ASRE pipeline runs (US-081).

Computes all 11 quality metrics from SPEC section 8.2 after each pipeline run.
Metrics are derived from scored encounters and per-stage metrics, then
converted to records for persistence in the asre_quality_metrics table.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Confidence score threshold below which an encounter is "low confidence"
_LOW_CONFIDENCE_THRESHOLD = 0.60

# Flag-to-metric mapping: flag name -> metric key
_FLAG_METRIC_MAP: dict[str, str] = {
    "DUPLICATE_DETECTED": "duplicate_rate",
    "MISSING_DISCHARGE": "missing_discharge_rate",
    "TIMESTAMP_MISMATCH": "reconciliation_mismatch_rate",
    "FACILITY_UNRESOLVED": "facility_unresolved_rate",
    "AUTH_WITHOUT_ADMIT": "auth_without_admit_rate",
    "CLAIMS_ONLY_ENCOUNTER": "claims_only_rate",
}


class QualityMetricComputer:
    """Computes quality metrics from scored encounters and stage metrics.

    Produces a dict of 12 metric name -> value pairs covering:
    - Rate metrics: duplicate_rate, missing_discharge_rate,
      reconciliation_mismatch_rate, low_confidence_rate,
      facility_unresolved_rate, auth_without_admit_rate, claims_only_rate,
      failed_event_rate
    - Aggregate metrics: avg_confidence_score, events_ingested,
      encounters_created, encounters_updated
    """

    def compute(
        self,
        encounters: list[Any],
        stage_metrics: list[dict[str, Any]],
        events_ingested: int,
        encounters_created: int,
        encounters_updated: int,
    ) -> dict[str, float]:
        """Compute all quality metrics for a pipeline run.

        Args:
            encounters: List of scored ReconciledEncounter objects.
            stage_metrics: Per-stage metric dicts from the pipeline runner.
            events_ingested: Total events ingested in this run.
            encounters_created: Number of new encounters created.
            encounters_updated: Number of existing encounters updated.

        Returns:
            Dict mapping metric name to numeric value.
        """
        total = len(encounters)

        # Count flag-based metrics
        flag_counts: dict[str, int] = {metric: 0 for metric in _FLAG_METRIC_MAP.values()}
        low_confidence_count = 0
        total_score = 0.0

        for enc in encounters:
            flags: list[str] = getattr(enc, "confidence_flags", [])
            score: float = getattr(enc, "confidence_score", 0.0)

            # Count each flag
            for flag, metric_key in _FLAG_METRIC_MAP.items():
                if flag in flags:
                    flag_counts[metric_key] += 1

            # Low confidence
            if score < _LOW_CONFIDENCE_THRESHOLD:
                low_confidence_count += 1

            total_score += score

        # Compute failed event rate from stage metrics
        total_records_in = 0
        total_errors = 0
        for m in stage_metrics:
            total_records_in += m.get("records_in", 0)
            total_errors += m.get("errors", 0)

        failed_event_rate = (
            total_errors / total_records_in if total_records_in > 0 else 0.0
        )

        # Build result
        metrics: dict[str, float] = {}

        # Rate metrics (flag-based)
        for metric_key, count in flag_counts.items():
            metrics[metric_key] = count / total if total > 0 else 0.0

        # Low confidence rate
        metrics["low_confidence_rate"] = (
            low_confidence_count / total if total > 0 else 0.0
        )

        # Aggregate metrics
        metrics["avg_confidence_score"] = total_score / total if total > 0 else 0.0
        metrics["events_ingested"] = float(events_ingested)
        metrics["encounters_created"] = float(encounters_created)
        metrics["encounters_updated"] = float(encounters_updated)
        metrics["failed_event_rate"] = failed_event_rate

        return metrics

    def evaluate_thresholds(
        self,
        metrics: dict[str, float],
        thresholds: dict[str, float],
    ) -> dict[str, str]:
        """Evaluate each metric against warn and fail thresholds.

        For each metric, looks up ``<metric_name>_warn`` and
        ``<metric_name>_fail`` keys in *thresholds*.  Status is determined as:

        - ``"fail"`` if value >= fail threshold
        - ``"warn"`` if value >= warn threshold (but below fail)
        - ``"pass"`` otherwise (or if no thresholds configured for that metric)

        Args:
            metrics: Dict from :meth:`compute`.
            thresholds: Dict of threshold keys from
                ``AlertingConfig.thresholds`` (e.g.
                ``{"duplicate_rate_warn": 0.05, "duplicate_rate_fail": 0.15}``).

        Returns:
            Dict mapping metric name to status string (``"pass"``,
            ``"warn"``, or ``"fail"``).
        """
        statuses: dict[str, str] = {}
        for name, value in metrics.items():
            warn_key = f"{name}_warn"
            fail_key = f"{name}_fail"
            warn_threshold = thresholds.get(warn_key)
            fail_threshold = thresholds.get(fail_key)

            if fail_threshold is not None and value >= fail_threshold:
                statuses[name] = "fail"
            elif warn_threshold is not None and value >= warn_threshold:
                statuses[name] = "warn"
            else:
                statuses[name] = "pass"
        return statuses

    def to_records(
        self,
        metrics: dict[str, float],
        run_id: str,
        statuses: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Convert computed metrics to row dicts for asre_quality_metrics table.

        Args:
            metrics: Dict from compute().
            run_id: Pipeline run ID.
            statuses: Optional dict from evaluate_thresholds(). When provided,
                each record includes a ``status`` field.

        Returns:
            List of dicts, one per metric, with run_id, metric_name,
            metric_value, computed_at, and optionally status fields.
        """
        now = datetime.now(tz=timezone.utc).isoformat()
        records: list[dict[str, Any]] = []
        for name, value in metrics.items():
            record: dict[str, Any] = {
                "run_id": run_id,
                "metric_name": name,
                "metric_value": value,
                "computed_at": now,
            }
            if statuses is not None:
                record["status"] = statuses.get(name, "pass")
            records.append(record)
        return records
