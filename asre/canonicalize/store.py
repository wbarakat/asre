"""Canonical event persistence for lookback stitching."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Iterable

from asre.canonicalize.timestamp_parser import parse_event_ts
from asre.migration.ddl_types import DDLTypeMapper, add_column_if_missing
from asre.models.canonical_event import CanonicalEvent


class CanonicalEventStore:
    """Persist and retrieve canonical events for incremental stitching."""

    TABLE_NAME = "asre_canonical_events"

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter

    def ensure_table(self) -> None:
        """Create the canonical events table if it doesn't exist."""
        warehouse_type = getattr(self._adapter, "warehouse_type", "postgres")
        m = DDLTypeMapper(warehouse_type)
        t = m.text()
        b = m.boolean()
        j = m.json()
        ts = m.timestamp()
        pk = m.primary_key("event_id")

        cols = [
            pk,
            f"patient_key {t} NOT NULL",
            f"event_type {t} NOT NULL",
            f"event_ts {ts} NOT NULL",
            f"source_system {t} NOT NULL",
            f"source_record_id {t} NOT NULL",
            f"facility_raw {t}",
            f"facility_canonical_id {t}",
            f"facility_match_type {t}",
            f"npi {t}",
            f"ccn {t}",
            f"admit_flag {b}",
            f"discharge_flag {b}",
            f"auth_flag {b}",
            f"patient_class {t}",
            f"drg {t}",
            f"principal_diagnosis {t}",
            f"diagnosis_codes {j}",
            f"auth_status {t}",
            f"payer_id {t}",
            f"ingested_at {ts}",
            f"batch_id {t}",
            f"raw_payload {j}",
            f"admitting_diagnosis {t}",
        ]

        col_str = ", ".join(cols)
        self._adapter.execute_ddl(
            f"CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} ({col_str})"
        )

        # Ensure columns added by later migrations exist on older installs
        add_column_if_missing(self._adapter, self.TABLE_NAME, "admitting_diagnosis", t)

    def upsert_events(self, events: Iterable[CanonicalEvent]) -> int:
        """Upsert canonical events by event_id."""
        records = [self._event_to_record(e) for e in events]
        if not records:
            return 0

        self.ensure_table()

        event_ids = [rec["event_id"] for rec in records]
        for chunk in _chunk(event_ids, 1000):
            ids_sql = ", ".join(_sql_literal(v) for v in chunk)
            self._adapter.execute_ddl(
                f"DELETE FROM {self.TABLE_NAME} WHERE event_id IN ({ids_sql})"  # nosec B608
            )

        count = int(self._adapter.write_records(self.TABLE_NAME, records))
        return count

    def fetch_recent_events(
        self,
        patient_keys: Iterable[str],
        *,
        since_ts: datetime,
    ) -> list[CanonicalEvent]:
        """Fetch canonical events for patient_keys on/after since_ts."""
        keys = [k for k in patient_keys if k]
        if not keys:
            return []

        self.ensure_table()

        results: list[CanonicalEvent] = []
        since_val = since_ts.isoformat()
        for chunk in _chunk(keys, 500):
            keys_sql = ", ".join(_sql_literal(v) for v in chunk)
            query = (
                f"SELECT * FROM {self.TABLE_NAME} "  # nosec B608
                f"WHERE patient_key IN ({keys_sql}) "
                f"AND event_ts >= :since_val"
            )
            rows = self._adapter.read_source(
                self.TABLE_NAME,
                query,  # nosec B608
                {"since_val": since_val},
            )
            for row in rows:
                results.append(self._row_to_event(row))

        return results

    @staticmethod
    def _event_to_record(event: CanonicalEvent) -> dict[str, Any]:
        """Serialize CanonicalEvent to DB record."""
        return {
            "event_id": event.event_id,
            "patient_key": event.patient_key,
            "event_type": event.event_type,
            "event_ts": event.event_ts,
            "source_system": event.source_system,
            "source_record_id": event.source_record_id,
            "facility_raw": event.facility_raw,
            "facility_canonical_id": event.facility_canonical_id,
            "facility_match_type": event.facility_match_type,
            "npi": event.npi,
            "ccn": event.ccn,
            "admit_flag": event.admit_flag,
            "discharge_flag": event.discharge_flag,
            "auth_flag": event.auth_flag,
            "patient_class": event.patient_class,
            "drg": event.drg,
            "principal_diagnosis": event.principal_diagnosis,
            "diagnosis_codes": json.dumps(event.diagnosis_codes, default=_json_default)
            if event.diagnosis_codes is not None
            else None,
            "auth_status": event.auth_status,
            "payer_id": event.payer_id,
            "ingested_at": event.ingested_at,
            "batch_id": event.batch_id,
            "raw_payload": json.dumps(event._raw_payload, default=_json_default)
            if event._raw_payload is not None
            else None,
        }

    @staticmethod
    def _row_to_event(row: dict[str, Any]) -> CanonicalEvent:
        """Deserialize DB row to CanonicalEvent."""
        diagnosis_codes = row.get("diagnosis_codes")
        if isinstance(diagnosis_codes, str):
            try:
                diagnosis_codes = json.loads(diagnosis_codes)
            except json.JSONDecodeError:
                diagnosis_codes = None

        raw_payload = row.get("raw_payload")
        if isinstance(raw_payload, str):
            try:
                raw_payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                raw_payload = None

        return CanonicalEvent(
            event_id=str(row.get("event_id")),
            patient_key=str(row.get("patient_key")),
            event_type=str(row.get("event_type")),
            event_ts=parse_event_ts(row.get("event_ts")),
            source_system=str(row.get("source_system")),
            source_record_id=str(row.get("source_record_id")),
            facility_raw=str(row.get("facility_raw") or ""),
            facility_canonical_id=row.get("facility_canonical_id"),
            facility_match_type=row.get("facility_match_type"),
            npi=row.get("npi"),
            ccn=row.get("ccn"),
            admit_flag=row.get("admit_flag"),
            discharge_flag=row.get("discharge_flag"),
            auth_flag=row.get("auth_flag"),
            patient_class=row.get("patient_class"),
            drg=row.get("drg"),
            principal_diagnosis=row.get("principal_diagnosis"),
            diagnosis_codes=diagnosis_codes,
            auth_status=row.get("auth_status"),
            payer_id=row.get("payer_id"),
            ingested_at=parse_event_ts(row.get("ingested_at")),
            batch_id=str(row.get("batch_id") or ""),
            _raw_payload=raw_payload,
        )


def _chunk(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
