"""Paired event emitter for claims sources.

When a claims source has paired_events configured, one source row
emits two CanonicalEvents: one for the admit and one for the discharge.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from asre.config.source_schema import FieldMappings, PairedEvents
from asre.models.canonical_event import CanonicalEvent
from asre.canonicalize.timestamp_parser import parse_event_ts
from asre.canonicalize.event_id import generate_event_id


class PairedEventEmitter:
    """Emits paired admit + discharge CanonicalEvents from a single claims row.

    Both events share patient_key, source_record_id, facility_raw, and
    optional fields. Each gets its own unique event_id, event_type,
    event_ts, and admit/discharge flags.
    """

    def __init__(self, field_mappings: FieldMappings, paired_events: PairedEvents) -> None:
        self.field_mappings = field_mappings
        self.paired_events = paired_events

    def emit(
        self,
        record: dict[str, Any],
        source_system: str,
        batch_id: str,
    ) -> list[CanonicalEvent]:
        """Emit two CanonicalEvents (admit + discharge) from one claims record.

        Args:
            record: Raw record dict from ingest stage.
            source_system: Source config name.
            batch_id: Pipeline batch ID.

        Returns:
            List of two CanonicalEvents: [admit_event, discharge_event].
        """
        fm = self.field_mappings
        pe = self.paired_events

        # Shared fields
        patient_key = str(record[fm.patient_key])
        source_record_id = str(record[fm.source_record_id])
        facility_raw = ""
        if fm.facility_raw is not None:
            raw_val = record.get(fm.facility_raw)
            if raw_val is not None:
                facility_raw = str(raw_val)

        # Optional shared fields
        payer_id = self._get_optional(record, fm.payer_id)
        drg = self._get_optional(record, fm.drg)
        principal_diagnosis = self._get_optional(record, fm.principal_diagnosis)
        patient_class = self._get_optional(record, fm.patient_class)
        raw_payload = record.get("_raw_payload")

        now = datetime.now(timezone.utc)

        # Admit event
        admit_event = CanonicalEvent(
            event_id=generate_event_id(
                source_system=source_system,
                source_record_id=source_record_id,
                event_type=pe.admit.event_type,
            ),
            patient_key=patient_key,
            event_type=pe.admit.event_type,
            event_ts=self._parse_event_ts(record[pe.admit.event_ts]),
            source_system=source_system,
            source_record_id=source_record_id,
            facility_raw=facility_raw,
            ingested_at=now,
            batch_id=batch_id,
            admit_flag=True,
            payer_id=payer_id,
            drg=drg,
            principal_diagnosis=principal_diagnosis,
            patient_class=patient_class,
            _raw_payload=raw_payload,
        )

        # Discharge event
        discharge_event = CanonicalEvent(
            event_id=generate_event_id(
                source_system=source_system,
                source_record_id=source_record_id,
                event_type=pe.discharge.event_type,
            ),
            patient_key=patient_key,
            event_type=pe.discharge.event_type,
            event_ts=self._parse_event_ts(record[pe.discharge.event_ts]),
            source_system=source_system,
            source_record_id=source_record_id,
            facility_raw=facility_raw,
            ingested_at=now,
            batch_id=batch_id,
            discharge_flag=True,
            payer_id=payer_id,
            drg=drg,
            principal_diagnosis=principal_diagnosis,
            patient_class=patient_class,
            _raw_payload=raw_payload,
        )

        return [admit_event, discharge_event]

    @staticmethod
    def _parse_event_ts(value: Any) -> datetime:
        """Parse event_ts from string or pass through datetime."""
        return parse_event_ts(value)

    @staticmethod
    def _get_optional(record: dict[str, Any], mapping_field: str | None) -> str | None:
        """Get an optional field value from the record using the mapping."""
        if mapping_field is None:
            return None
        val = record.get(mapping_field)
        if val is None:
            return None
        return str(val)
