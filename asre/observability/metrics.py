"""Per-stage metrics tracking for ASRE pipeline stages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class StageMetrics:
    """Tracks timing, throughput, and error counts for a pipeline stage.

    Use as a context manager to auto-capture timing::

        with StageMetrics('ingest', run_id) as m:
            m.records_in = 100
            m.records_out = 95
    """

    def __init__(self, stage_name: str, run_id: str) -> None:
        self.stage_name = stage_name
        self.run_id = run_id
        self.records_in: int = 0
        self.records_out: int = 0
        self.errors: int = 0
        self.status: str = "pending"
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None

    def __enter__(self) -> StageMetrics:
        self.started_at = datetime.now(timezone.utc)
        self.status = "running"
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.completed_at = datetime.now(timezone.utc)
        if exc_type is not None:
            self.status = "failed"
        else:
            self.status = "success"

    def to_dict(self) -> dict[str, Any]:
        """Serialize metrics for persistence to asre_run_metrics table."""
        return {
            "stage_name": self.stage_name,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "records_in": self.records_in,
            "records_out": self.records_out,
            "errors": self.errors,
            "status": self.status,
        }
