"""MaterializeStage - pipeline stage for encounter materialization (US-072).

Writes scored encounters to the admission_events_unified table using
merge/upsert keyed on encounter_id. New encounters get created_at set;
updated encounters get updated_at set. All fields from SPEC §3.4 are populated.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.readmission.detector import ReadmissionDetector
from asre.reconcile.stage import ReconciledEncounter

logger = logging.getLogger(__name__)

ASRE_VERSION = "0.1.0"

TABLE_NAME = "admission_events_unified"
DETAIL_TABLE_NAME = "asre_encounters_detail"


# Admit and discharge event types for role assignment
_ADMIT_EVENT_TYPES = {"ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START"}
_DISCHARGE_EVENT_TYPES = {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"}


def _extract_source_type(source_system: str) -> str:
    """Extract source type prefix from source_system name."""
    lower = source_system.lower()
    for prefix in ("claims", "auth", "adt"):
        if lower.startswith(prefix):
            return prefix
    return lower


def assign_event_roles(enc: ReconciledEncounter) -> None:
    """Assign role_in_encounter to each event in the encounter.

    Roles:
    - admit_anchor: event whose timestamp matches reconciled admit_ts
    - discharge_anchor: event whose timestamp matches reconciled discharge_ts
    - duplicate: preserved from dedup stage (already set)
    - supporting: all other events
    """
    if enc.reconciled_timestamps is None:
        # No reconciled timestamps — mark all non-duplicates as supporting
        for event in enc.events:
            if event.role_in_encounter != "duplicate":
                event.role_in_encounter = "supporting"
        return

    admit_ts = enc.reconciled_timestamps.admit_ts
    discharge_ts = enc.reconciled_timestamps.discharge_ts

    admit_anchor_found = False
    discharge_anchor_found = False

    for event in enc.events:
        # Skip events already marked as duplicate
        if event.role_in_encounter == "duplicate":
            continue

        # Check for admit anchor: matching timestamp + admit event type
        if (
            not admit_anchor_found
            and event.event_ts == admit_ts
            and event.event_type in _ADMIT_EVENT_TYPES
        ):
            event.role_in_encounter = "admit_anchor"
            admit_anchor_found = True
        # Check for discharge anchor: matching timestamp + discharge event type
        elif (
            not discharge_anchor_found
            and discharge_ts is not None
            and event.event_ts == discharge_ts
            and event.event_type in _DISCHARGE_EVENT_TYPES
        ):
            event.role_in_encounter = "discharge_anchor"
            discharge_anchor_found = True
        else:
            event.role_in_encounter = "supporting"


def event_to_detail_record(
    event: CanonicalEvent,
    encounter_id: str,
) -> dict[str, Any]:
    """Convert a CanonicalEvent to a flat dict for asre_encounters_detail."""
    return {
        "encounter_id": encounter_id,
        "event_id": event.event_id,
        "event_type": event.event_type,
        "event_ts": _ts_str(event.event_ts),
        "source_system": event.source_system,
        "role_in_encounter": event.role_in_encounter,
    }


def encounter_to_record(
    enc: ReconciledEncounter,
    now: datetime,
    run_id: str,
) -> dict[str, Any]:
    """Convert a ReconciledEncounter to a flat dict for the admission_events_unified table.

    Uses reconciled timestamps and classification when available,
    falling back to the underlying StitchedEncounter fields.
    """
    # Determine timestamps from reconciliation
    admit_ts: datetime | None
    discharge_ts: datetime | None
    admit_source_priority: str | None
    discharge_source_priority: str | None
    if enc.reconciled_timestamps is not None:
        admit_ts = enc.reconciled_timestamps.admit_ts
        discharge_ts = enc.reconciled_timestamps.discharge_ts
        admit_source_priority = enc.reconciled_timestamps.admit_source_priority
        discharge_source_priority = enc.reconciled_timestamps.discharge_source_priority
    else:
        # Fallback: derive from events
        admit_ts = _earliest_admit_ts(enc)
        discharge_ts = _latest_discharge_ts(enc)
        admit_source_priority = None
        discharge_source_priority = None

    # Determine classification from reconciliation
    if enc.reconciled_classification is not None:
        encounter_type = enc.reconciled_classification.encounter_type
        drg = enc.reconciled_classification.drg
        payer_id = enc.reconciled_classification.payer_id
        principal_diagnosis = enc.reconciled_classification.principal_diagnosis
        admitting_diagnosis = enc.reconciled_classification.admitting_diagnosis
        diagnosis_codes = enc.reconciled_classification.diagnosis_codes
    else:
        encounter_type = enc.encounter_type or "outpatient"
        drg = None
        payer_id = None
        principal_diagnosis = None
        admitting_diagnosis = None
        diagnosis_codes = []

    # Compute LOS
    los_hours: float | None = None
    if admit_ts is not None and discharge_ts is not None:
        delta = discharge_ts - admit_ts
        los_hours = delta.total_seconds() / 3600.0

    # Source info
    events = enc.events
    source_event_ids = [e.event_id for e in events]
    source_systems = list({e.source_system for e in events})
    source_types = {_extract_source_type(s) for s in source_systems}
    has_adt = "adt" in source_types
    has_claims = "claims" in source_types
    has_auth = "auth" in source_types

    # Facility info
    facility_canonical_id = enc.facility_canonical_id or ""
    facility_name = facility_canonical_id  # Best available; registry lookup is external
    is_acute = _is_acute_type(enc, facility_canonical_id)

    # Transfer chain
    transfer_chain: list[str] | None = None
    if enc.transfer_chain:
        transfer_chain = [str(idx) for idx in enc.transfer_chain]

    record: dict[str, Any] = {
        "encounter_id": enc.encounter_id,
        "patient_key": enc.patient_key,
        "encounter_type": encounter_type,
        "status": enc.status,
        "admit_ts": _ts_str(admit_ts),
        "discharge_ts": _ts_str(discharge_ts),
        "los_hours": los_hours,
        "facility_canonical_id": facility_canonical_id,
        "facility_name": facility_name,
        "is_acute": is_acute,
        "source_event_ids": json.dumps(source_event_ids),
        "source_systems": json.dumps(source_systems),
        "has_adt": has_adt,
        "has_claims": has_claims,
        "has_auth": has_auth,
        "confidence_score": enc.confidence_score,
        "confidence_flags": json.dumps(enc.confidence_flags),
        "admit_source_priority": admit_source_priority,
        "discharge_source_priority": discharge_source_priority,
        "payer_id": payer_id,
        "drg": drg,
        "principal_diagnosis": principal_diagnosis,
        "admitting_diagnosis": admitting_diagnosis,
        "diagnosis_codes": json.dumps(diagnosis_codes) if diagnosis_codes else None,
        "is_readmission": getattr(enc, "is_readmission", None),
        "readmission_days": getattr(enc, "readmission_days", None),
        "obs_to_ip_conversion": enc.obs_to_ip_conversion,
        "transfer_chain": json.dumps(transfer_chain) if transfer_chain else None,
        "episode_id": None,
        "created_at": _ts_str(now),
        "updated_at": _ts_str(now),
        "asre_version": ASRE_VERSION,
    }
    return record


def _earliest_admit_ts(enc: ReconciledEncounter) -> datetime | None:
    """Get the earliest admit/arrival event timestamp."""
    admit_types = {"ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START"}
    admit_events = [e for e in enc.events if e.event_type in admit_types]
    if admit_events:
        result: datetime = min(e.event_ts for e in admit_events)
        return result
    if enc.events:
        ts: datetime = enc.events[0].event_ts
        return ts
    return None


def _latest_discharge_ts(enc: ReconciledEncounter) -> datetime | None:
    """Get the latest discharge event timestamp."""
    discharge_types = {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"}
    discharge_events = [e for e in enc.events if e.event_type in discharge_types]
    if discharge_events:
        result: datetime = max(e.event_ts for e in discharge_events)
        return result
    return None


def _is_acute_type(enc: ReconciledEncounter, facility_id: str) -> bool:
    """Determine if the encounter is at an acute facility.

    This is a best-effort check. True if encounter_type is inpatient.
    """
    return (enc.encounter_type or "").lower() in ("inpatient", "ip")


def _ts_str(ts: datetime | None) -> str | None:
    """Convert datetime to ISO string or None."""
    if ts is None:
        return None
    return ts.isoformat()


class MaterializeStage(PipelineStage):
    """Pipeline stage that materializes encounters to the admission_events_unified table.

    Performs merge/upsert keyed on encounter_id. New encounters get INSERT
    with created_at. Updated encounters get UPDATE with updated_at.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("materialize", "")
        self.encounters_in: list[ReconciledEncounter] = []
        self.encounters_materialized: int = 0
        self.encounters_inserted: int = 0
        self.encounters_updated: int = 0
        self.detail_rows_written: int = 0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the materialize stage.

        Converts scored encounters to records and writes them to the
        admission_events_unified table using merge/upsert.
        """
        self.metrics = StageMetrics("materialize", context.run_id)

        with self.metrics:
            encounters = list(self.encounters_in)
            self.metrics.records_in = len(encounters)

            adapter = context.config.get("adapter")
            now = datetime.now(tz=timezone.utc)

            if adapter is None:
                logger.warning(
                    "No adapter configured — skipping materialization"
                )
                self.metrics.records_out = 0
                return batch

            # Run readmission detection before materialization
            facility_type_map: dict[str, str] = context.config.get(
                "facility_registry_map", {}
            )
            readmission_detector = ReadmissionDetector(
                facility_type_map=facility_type_map
            )
            readmission_detector.detect(encounters)

            # Ensure tables exist
            self._ensure_table(adapter)
            self._ensure_detail_table(adapter)

            # Load existing encounter_ids for upsert logic
            existing_ids = self._load_existing_ids(adapter)

            insert_records: list[dict[str, Any]] = []
            update_records: list[dict[str, Any]] = []
            detail_records: list[dict[str, Any]] = []

            for enc in encounters:
                # Assign roles to events before materialization
                assign_event_roles(enc)

                record = encounter_to_record(enc, now, context.run_id)
                if record["encounter_id"] in existing_ids:
                    # Preserve original created_at for updates
                    record["created_at"] = existing_ids[record["encounter_id"]]
                    update_records.append(record)
                else:
                    insert_records.append(record)

                # Build detail rows for each event
                enc_id = enc.encounter_id or ""
                for event in enc.events:
                    detail_records.append(
                        event_to_detail_record(event, enc_id)
                    )

            # Write inserts
            if insert_records:
                count: int = adapter.write_records(TABLE_NAME, insert_records)
                self.encounters_inserted = count

            # Write updates via DELETE + INSERT (simple upsert for Postgres)
            if update_records:
                for rec in update_records:
                    self._delete_by_id(adapter, rec["encounter_id"])
                count = adapter.write_records(TABLE_NAME, update_records)
                self.encounters_updated = count

            # Write detail rows
            if detail_records:
                detail_count: int = adapter.write_records(
                    DETAIL_TABLE_NAME, detail_records
                )
                self.detail_rows_written = detail_count

            self.encounters_materialized = (
                self.encounters_inserted + self.encounters_updated
            )
            self.metrics.records_out = self.encounters_materialized

        return batch

    def _ensure_table(self, adapter: Any) -> None:
        """Create the admission_events_unified table if it doesn't exist."""
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} ("
            "encounter_id TEXT PRIMARY KEY, "
            "patient_key TEXT NOT NULL, "
            "encounter_type TEXT NOT NULL, "
            "status TEXT NOT NULL, "
            "admit_ts TEXT, "
            "discharge_ts TEXT, "
            "los_hours REAL, "
            "facility_canonical_id TEXT, "
            "facility_name TEXT, "
            "is_acute BOOLEAN, "
            "source_event_ids TEXT, "
            "source_systems TEXT, "
            "has_adt BOOLEAN, "
            "has_claims BOOLEAN, "
            "has_auth BOOLEAN, "
            "confidence_score REAL, "
            "confidence_flags TEXT, "
            "admit_source_priority TEXT, "
            "discharge_source_priority TEXT, "
            "payer_id TEXT, "
            "drg TEXT, "
            "principal_diagnosis TEXT, "
            "admitting_diagnosis TEXT, "
            "diagnosis_codes TEXT, "
            "is_readmission BOOLEAN, "
            "readmission_days INTEGER, "
            "obs_to_ip_conversion BOOLEAN, "
            "transfer_chain TEXT, "
            "episode_id TEXT, "
            "created_at TEXT, "
            "updated_at TEXT, "
            "asre_version TEXT"
            ")"
        )
        adapter.execute_ddl(ddl)

    def _ensure_detail_table(self, adapter: Any) -> None:
        """Create the asre_encounters_detail table if it doesn't exist."""
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {DETAIL_TABLE_NAME} ("
            "encounter_id TEXT NOT NULL, "
            "event_id TEXT NOT NULL, "
            "event_type TEXT NOT NULL, "
            "event_ts TEXT, "
            "source_system TEXT, "
            "role_in_encounter TEXT, "
            "PRIMARY KEY (encounter_id, event_id)"
            ")"
        )
        adapter.execute_ddl(ddl)

    def _load_existing_ids(self, adapter: Any) -> dict[str, str]:
        """Load existing encounter_ids and their created_at from the table.

        Returns dict mapping encounter_id -> created_at string.
        """
        try:
            rows: list[dict[str, Any]] = adapter.read_source(
                TABLE_NAME,
                f"SELECT encounter_id, created_at FROM {TABLE_NAME}",
            )
            return {
                row["encounter_id"]: row["created_at"] for row in rows
            }
        except Exception:
            # Table might not have data yet
            return {}

    def _delete_by_id(self, adapter: Any, encounter_id: str) -> None:
        """Delete a single encounter by ID for upsert."""
        from sqlalchemy import text  # noqa: PLC0415

        if hasattr(adapter, "_connection") and adapter._connection is not None:
            adapter._connection.execute(
                text(f"DELETE FROM {TABLE_NAME} WHERE encounter_id = :eid"),
                {"eid": encounter_id},
            )
            adapter._connection.commit()
