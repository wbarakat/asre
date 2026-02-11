"""Field mapper - maps source columns to canonical event fields."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from asre.config.source_schema import FieldMappings
from asre.models.canonical_event import CanonicalEvent
from asre.canonicalize.timestamp_parser import parse_event_ts


class FieldMapper:
    """Maps raw record dicts to CanonicalEvent using configured field mappings.

    Handles:
    - Required field mapping (patient_key, event_ts, source_record_id, facility_raw)
    - Optional field mapping (patient_class, payer_id, drg, principal_diagnosis, etc.)
    - UUID generation for event_id
    - ingested_at timestamp
    - batch_id and source_system from context

    Does NOT handle event_type resolution (see EventTypeResolver).
    """

    def __init__(self, field_mappings: FieldMappings) -> None:
        self.field_mappings = field_mappings

    def map_record(
        self,
        record: dict[str, Any],
        source_system: str,
        batch_id: str,
    ) -> CanonicalEvent:
        """Map a raw record dict to a CanonicalEvent.

        Args:
            record: Raw record dict from ingest stage.
            source_system: Source config name (e.g., "adt_vendor_x").
            batch_id: Pipeline batch ID.

        Returns:
            A CanonicalEvent with mapped fields.
        """
        fm = self.field_mappings

        # Required fields
        patient_key = str(record[fm.patient_key])
        source_record_id = str(record[fm.source_record_id])
        event_ts = self._parse_event_ts(record[fm.event_ts])

        # facility_raw: required on CanonicalEvent but mapping is optional
        facility_raw = ""
        if fm.facility_raw is not None:
            raw_val = record.get(fm.facility_raw)
            if raw_val is not None:
                facility_raw = str(raw_val)

        # Optional fields
        patient_class = self._get_optional(record, fm.patient_class)
        payer_id = self._get_optional(record, fm.payer_id)
        drg = self._get_optional(record, fm.drg)
        principal_diagnosis = self._get_optional(record, fm.principal_diagnosis)
        npi = self._get_optional(record, fm.npi)
        ccn = self._get_optional(record, fm.ccn)
        facility_canonical_id = self._get_optional(record, fm.facility_canonical_id)
        facility_name = self._get_optional(record, fm.facility_name)

        return CanonicalEvent(
            event_id=str(uuid.uuid4()),
            patient_key=patient_key,
            event_type="UNKNOWN",
            event_ts=event_ts,
            source_system=source_system,
            source_record_id=source_record_id,
            facility_raw=facility_raw,
            ingested_at=datetime.now(timezone.utc),
            batch_id=batch_id,
            patient_class=patient_class,
            payer_id=payer_id,
            drg=drg,
            principal_diagnosis=principal_diagnosis,
            facility_canonical_id=facility_canonical_id,
            facility_match_type="customer_provided" if facility_canonical_id else None,
            facility_name=facility_name,
            npi=npi,
            ccn=ccn,
            _raw_payload=record.get("_raw_payload"),
        )

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
