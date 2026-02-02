"""Audit logger for ASRE pipeline (US-075).

Tracks all encounter modifications in asre_audit_log table.
Each create/update generates an audit log entry with action,
entity type, entity ID, and detail about what changed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


AUDIT_TABLE_NAME = "asre_audit_log"


class AuditLogger:
    """Logs pipeline actions to the asre_audit_log table.

    Each log entry contains: log_id, run_id, timestamp, action,
    entity_type, entity_id, detail.

    Valid actions: ingest, stitch, dedup, reconcile, score, normalize, materialize.
    """

    def __init__(self, adapter: Any, run_id: str) -> None:
        self._adapter = adapter
        self._run_id = run_id

    def ensure_table(self) -> None:
        """Create the asre_audit_log table if it does not exist."""
        self._adapter.execute_ddl(
            f"CREATE TABLE IF NOT EXISTS {AUDIT_TABLE_NAME} ("
            "log_id TEXT PRIMARY KEY, "
            "run_id TEXT NOT NULL, "
            "timestamp TEXT NOT NULL, "
            "action TEXT NOT NULL, "
            "entity_type TEXT NOT NULL, "
            "entity_id TEXT NOT NULL, "
            "detail TEXT"
            ")"
        )

    def log(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        detail: str,
    ) -> None:
        """Write a single audit log entry."""
        record = self._build_record(action, entity_type, entity_id, detail)
        self._adapter.write_records(AUDIT_TABLE_NAME, [record])

    def log_batch(self, entries: list[dict[str, str]]) -> None:
        """Write multiple audit log entries at once.

        Each entry dict must have: action, entity_type, entity_id, detail.
        """
        records = [
            self._build_record(
                entry["action"],
                entry["entity_type"],
                entry["entity_id"],
                entry["detail"],
            )
            for entry in entries
        ]
        self._adapter.write_records(AUDIT_TABLE_NAME, records)

    def _build_record(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        detail: str,
    ) -> dict[str, Any]:
        now = datetime.now(tz=timezone.utc).isoformat()
        return {
            "log_id": str(uuid.uuid4()),
            "run_id": self._run_id,
            "timestamp": now,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "detail": detail,
        }
