"""Tests for FieldMapper - maps source columns to canonical event fields."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

from asre.canonicalize.mapper import FieldMapper
from asre.config.source_schema import FieldMappings
from asre.models.canonical_event import CanonicalEvent


def _adt_field_mappings() -> FieldMappings:
    """Example ADT field mappings matching test_customer config."""
    return FieldMappings(
        patient_key="patient_mrn",
        event_ts="message_ts",
        source_record_id="message_control_id",
        facility_raw="sending_facility",
        patient_class="patient_class",
        npi="facility_npi",
    )


def _sample_adt_record() -> dict[str, Any]:
    """Sample raw ADT record as returned from ingest stage."""
    return {
        "patient_mrn": "MRN001",
        "message_ts": "2024-01-15T10:30:00",
        "message_control_id": "MSG-12345",
        "sending_facility": "St. Mary's Medical Center",
        "patient_class": "I",
        "facility_npi": "1234567890",
        "hl7_event": "A01",
        "_source_name": "adt_vendor_x",
        "_source_type": "adt",
        "_raw_payload": {"patient_mrn": "MRN001", "message_ts": "2024-01-15T10:30:00"},
    }


class TestFieldMapperConstruction:
    """Tests for FieldMapper initialization."""

    def test_creates_with_field_mappings(self) -> None:
        mappings = _adt_field_mappings()
        mapper = FieldMapper(mappings)
        assert mapper.field_mappings is mappings

    def test_importable_from_module(self) -> None:
        from asre.canonicalize.mapper import FieldMapper as FM
        assert FM is FieldMapper


class TestFieldMapperMapping:
    """Tests for mapping raw records to canonical events."""

    def test_maps_required_fields(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(
            record=record,
            source_system="adt_vendor_x",
            batch_id="batch_001",
        )

        assert isinstance(event, CanonicalEvent)
        assert event.patient_key == "MRN001"
        assert event.source_record_id == "MSG-12345"
        assert event.facility_raw == "St. Mary's Medical Center"
        assert event.source_system == "adt_vendor_x"
        assert event.batch_id == "batch_001"

    def test_maps_event_ts_as_datetime(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(
            record=record,
            source_system="adt_vendor_x",
            batch_id="batch_001",
        )

        assert isinstance(event.event_ts, datetime)
        assert event.event_ts.year == 2024
        assert event.event_ts.month == 1
        assert event.event_ts.day == 15

    def test_handles_datetime_object_in_event_ts(self) -> None:
        """event_ts might already be a datetime from the adapter."""
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()
        record["message_ts"] = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        event = mapper.map_record(
            record=record,
            source_system="adt_vendor_x",
            batch_id="batch_001",
        )

        assert isinstance(event.event_ts, datetime)
        assert event.event_ts.year == 2024

    def test_generates_uuid_event_id(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(
            record=record,
            source_system="adt_vendor_x",
            batch_id="batch_001",
        )

        # Should be a valid UUID string
        parsed = uuid.UUID(event.event_id)
        assert str(parsed) == event.event_id

    def test_generates_unique_event_ids(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event1 = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")
        event2 = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event1.event_id != event2.event_id

    def test_sets_ingested_at_to_current_time(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        before = datetime.now(timezone.utc)
        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")
        after = datetime.now(timezone.utc)

        assert before <= event.ingested_at <= after

    def test_maps_optional_fields_when_present(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.patient_class == "I"

    def test_unmapped_optional_fields_are_none(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        # These fields are not in the ADT mapping
        assert event.drg is None
        assert event.principal_diagnosis is None
        assert event.diagnosis_codes is None
        assert event.auth_status is None
        assert event.payer_id is None

    def test_preserves_raw_payload(self) -> None:
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event._raw_payload == record.get("_raw_payload")

    def test_event_type_defaults_to_unknown(self) -> None:
        """FieldMapper doesn't resolve event types — that's EventTypeResolver's job.

        event_type should be set to a placeholder since it's required on CanonicalEvent.
        """
        mapper = FieldMapper(_adt_field_mappings())
        record = _sample_adt_record()

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.event_type == "UNKNOWN"

    def test_facility_raw_none_when_not_mapped(self) -> None:
        """When facility_raw mapping is None, use empty string (required field)."""
        mappings = FieldMappings(
            patient_key="patient_mrn",
            event_ts="message_ts",
            source_record_id="message_control_id",
            # facility_raw not set (None)
        )
        mapper = FieldMapper(mappings)
        record = _sample_adt_record()

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.facility_raw == ""

    def test_maps_payer_id_when_configured(self) -> None:
        mappings = FieldMappings(
            patient_key="patient_mrn",
            event_ts="message_ts",
            source_record_id="message_control_id",
            payer_id="insurance_plan_id",
        )
        mapper = FieldMapper(mappings)
        record = _sample_adt_record()
        record["insurance_plan_id"] = "PAYER_123"

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.payer_id == "PAYER_123"

    def test_maps_drg_when_configured(self) -> None:
        mappings = FieldMappings(
            patient_key="patient_mrn",
            event_ts="message_ts",
            source_record_id="message_control_id",
            drg="drg_code",
        )
        mapper = FieldMapper(mappings)
        record = _sample_adt_record()
        record["drg_code"] = "470"

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.drg == "470"

    def test_maps_principal_diagnosis_when_configured(self) -> None:
        mappings = FieldMappings(
            patient_key="patient_mrn",
            event_ts="message_ts",
            source_record_id="message_control_id",
            principal_diagnosis="primary_dx",
        )
        mapper = FieldMapper(mappings)
        record = _sample_adt_record()
        record["primary_dx"] = "J18.9"

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.principal_diagnosis == "J18.9"

    def test_source_column_missing_in_record_returns_none_for_optional(self) -> None:
        """If a mapped source column doesn't exist in the record, optional field stays None."""
        mappings = FieldMappings(
            patient_key="patient_mrn",
            event_ts="message_ts",
            source_record_id="message_control_id",
            payer_id="insurance_plan_id",  # mapped but not in record
        )
        mapper = FieldMapper(mappings)
        record = _sample_adt_record()
        # record does NOT have "insurance_plan_id"

        event = mapper.map_record(record=record, source_system="adt_vendor_x", batch_id="batch_001")

        assert event.payer_id is None
