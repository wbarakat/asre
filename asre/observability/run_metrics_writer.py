"""Run metrics writer for ASRE pipeline (US-076).

Writes per-stage timing and throughput metrics to asre_run_metrics table
after each pipeline run. All 9 stages produce metrics rows with fields:
run_id, stage_name, started_at, completed_at, records_in, records_out,
errors, status.
"""

from __future__ import annotations

from typing import Any


RUN_METRICS_TABLE = "asre_run_metrics"


class RunMetricsWriter:
    """Persists per-stage pipeline metrics to the asre_run_metrics table.

    Pattern follows AuditLogger and CheckpointManager: ensure_table() creates
    the DDL, then write_metrics() batch-writes all stage metrics.
    """

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    def ensure_table(self) -> None:
        """Create the asre_run_metrics table if it does not exist."""
        self._adapter.execute_ddl(
            f"CREATE TABLE IF NOT EXISTS {RUN_METRICS_TABLE} ("
            "run_id TEXT NOT NULL, "
            "stage_name TEXT NOT NULL, "
            "started_at TEXT, "
            "completed_at TEXT, "
            "records_in INTEGER, "
            "records_out INTEGER, "
            "errors INTEGER, "
            "status TEXT, "
            "PRIMARY KEY (run_id, stage_name)"
            ")"
        )

    def write_metrics(self, metrics_list: list[dict[str, Any]]) -> None:
        """Write a list of stage metrics dicts to the run metrics table.

        Each dict should match the output of StageMetrics.to_dict().
        Empty lists are silently ignored.
        """
        if not metrics_list:
            return
        self._adapter.write_records(RUN_METRICS_TABLE, metrics_list)
