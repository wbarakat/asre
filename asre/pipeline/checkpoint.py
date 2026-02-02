"""Checkpoint manager for ASRE pipeline stage persistence.

Stores checkpoint state in asre_checkpoints table so failed runs
can be resumed from the last completed stage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from asre.ingest.base import IngestAdapter


class CheckpointManager:
    """Manages pipeline checkpoint state for resume support.

    Stores run progress in asre_checkpoints table with:
    run_id, last_completed_stage, stage_index, status, error, updated_at.
    """

    _TABLE = "asre_checkpoints"

    def __init__(self, adapter: IngestAdapter) -> None:
        self._adapter = adapter

    def ensure_table(self) -> None:
        """Create the asre_checkpoints table if it does not exist."""
        self._adapter.execute_ddl(
            "CREATE TABLE IF NOT EXISTS asre_checkpoints ("
            "run_id TEXT PRIMARY KEY, "
            "last_completed_stage TEXT NOT NULL, "
            "stage_index INTEGER NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'in_progress', "
            "error TEXT, "
            "updated_at TEXT NOT NULL"
            ")"
        )

    def save_checkpoint(
        self,
        run_id: str,
        stage_name: str,
        stage_index: int,
    ) -> None:
        """Save a checkpoint after a stage completes successfully."""
        now = datetime.now(tz=timezone.utc).isoformat()
        record: dict[str, Any] = {
            "run_id": run_id,
            "last_completed_stage": stage_name,
            "stage_index": stage_index,
            "status": "in_progress",
            "error": None,
            "updated_at": now,
        }
        self._adapter.write_records(self._TABLE, [record])

    def mark_completed(self, run_id: str) -> None:
        """Mark a run as fully completed."""
        now = datetime.now(tz=timezone.utc).isoformat()
        record: dict[str, Any] = {
            "run_id": run_id,
            "last_completed_stage": "quality_check",
            "stage_index": 8,
            "status": "completed",
            "error": None,
            "updated_at": now,
        }
        self._adapter.write_records(self._TABLE, [record])

    def mark_failed(
        self,
        run_id: str,
        stage_name: str,
        stage_index: int,
        error: str,
    ) -> None:
        """Mark a run as failed at a specific stage."""
        now = datetime.now(tz=timezone.utc).isoformat()
        record: dict[str, Any] = {
            "run_id": run_id,
            "last_completed_stage": stage_name,
            "stage_index": stage_index,
            "status": "failed",
            "error": error,
            "updated_at": now,
        }
        self._adapter.write_records(self._TABLE, [record])

    def load_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        """Load checkpoint state for a given run_id.

        Returns None if no checkpoint exists for the run_id.
        """
        try:
            rows = self._adapter.read_source(
                self._TABLE,
                f"SELECT * FROM {self._TABLE} WHERE run_id = '{run_id}'",
            )
        except Exception:
            return None

        if not rows:
            return None
        return dict(rows[0])
