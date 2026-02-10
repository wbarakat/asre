"""Checkpoint manager for ASRE pipeline stage persistence.

Stores checkpoint state in asre_checkpoints table so failed runs
can be resumed from the last completed stage.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from asre.ingest.base import IngestAdapter

logger = logging.getLogger(__name__)


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
        self._upsert_record(record)

    def mark_completed(self, run_id: str, stage_name: str, stage_index: int) -> None:
        """Mark a run as fully completed."""
        now = datetime.now(tz=timezone.utc).isoformat()
        record: dict[str, Any] = {
            "run_id": run_id,
            "last_completed_stage": stage_name,
            "stage_index": stage_index,
            "status": "completed",
            "error": None,
            "updated_at": now,
        }
        self._upsert_record(record)

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
        self._upsert_record(record)

    def _upsert_record(self, record: dict[str, Any]) -> None:
        """Upsert a checkpoint record using warehouse-appropriate SQL."""
        wt = getattr(self._adapter, "warehouse_type", "postgres")

        cols = [
            "run_id",
            "last_completed_stage",
            "stage_index",
            "status",
            "error",
            "updated_at",
        ]
        values = {col: record.get(col) for col in cols}

        def _sql_value(value: Any) -> str:
            if value is None:
                return "NULL"
            if isinstance(value, (int, float)):
                return str(value)
            text = str(value).replace("'", "''")
            return f"'{text}'"

        if wt == "redshift":
            self._adapter.execute_ddl(
                f"DELETE FROM {self._TABLE} WHERE run_id = {_sql_value(values['run_id'])}"  # nosec B608
            )
            columns = ", ".join(cols)
            vals = ", ".join(_sql_value(values[col]) for col in cols)
            self._adapter.execute_ddl(
                f"INSERT INTO {self._TABLE} ({columns}) VALUES ({vals})"  # nosec B608
            )
            return

        if wt in ("snowflake", "bigquery"):
            source_cols = ", ".join(
                f"{_sql_value(values[col])} AS {col}" for col in cols
            )
            merge_sql = (
                f"MERGE INTO {self._TABLE} AS target "  # nosec B608
                f"USING (SELECT {source_cols}) AS source "
                "ON target.run_id = source.run_id "
                "WHEN MATCHED THEN UPDATE SET "
                "last_completed_stage = source.last_completed_stage, "
                "stage_index = source.stage_index, "
                "status = source.status, "
                "error = source.error, "
                "updated_at = source.updated_at "
                "WHEN NOT MATCHED THEN INSERT "
                "(run_id, last_completed_stage, stage_index, status, error, updated_at) "
                "VALUES (source.run_id, source.last_completed_stage, source.stage_index, "
                "source.status, source.error, source.updated_at)"
            )
            self._adapter.execute_ddl(merge_sql)
            return

        # Postgres (default)
        columns = ", ".join(cols)
        vals = ", ".join(_sql_value(values[col]) for col in cols)
        updates = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in cols if col != "run_id"
        )
        sql = (
            f"INSERT INTO {self._TABLE} ({columns}) VALUES ({vals}) "  # nosec B608
            "ON CONFLICT (run_id) DO UPDATE SET "
            f"{updates}"
        )
        self._adapter.execute_ddl(sql)

    def load_checkpoint(self, run_id: str) -> dict[str, Any] | None:
        """Load checkpoint state for a given run_id.

        Returns None if no checkpoint exists for the run_id.
        """
        try:
            rows = self._adapter.read_source(
                self._TABLE,
                f"SELECT * FROM {self._TABLE} WHERE run_id = :run_id",  # nosec B608
                {"run_id": run_id},
            )
        except Exception:
            logger.debug("Could not load checkpoint for run_id=%s (table may not exist)", run_id)
            return None

        if not rows:
            return None
        return dict(rows[0])
