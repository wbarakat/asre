"""Tests for CanonicalEvent dataclass."""

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent


class TestCanonicalEvent:
    def test_construct_with_all_required_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        event = CanonicalEvent(
            event_id="evt-001",
            patient_key="patient-123",
            event_type="ADMIT",
            event_ts=now,
            source_system="adt_vendor_x",
            source_record_id="src-001",
            facility_raw="St. Mary's Hospital",
            ingested_at=now,
            batch_id="batch-001",
        )
        assert event.event_id == "evt-001"
        assert event.patient_key == "patient-123"
        assert event.event_type == "ADMIT"
        assert event.event_ts == now
        assert event.source_system == "adt_vendor_x"
        assert event.source_record_id == "src-001"
        assert event.facility_raw == "St. Mary's Hospital"
        assert event.ingested_at == now
        assert event.batch_id == "batch-001"

    def test_optional_fields_default_to_none(self) -> None:
        now = datetime.now(tz=timezone.utc)
        event = CanonicalEvent(
            event_id="evt-002",
            patient_key="patient-456",
            event_type="DISCHARGE",
            event_ts=now,
            source_system="claims",
            source_record_id="src-002",
            facility_raw="Memorial Hospital",
            ingested_at=now,
            batch_id="batch-001",
        )
        assert event.facility_canonical_id is None
        assert event.admit_flag is None
        assert event.discharge_flag is None
        assert event.auth_flag is None
        assert event.patient_class is None
        assert event.drg is None
        assert event.principal_diagnosis is None
        assert event.diagnosis_codes is None
        assert event.auth_status is None
        assert event.payer_id is None
        assert event._raw_payload is None

    def test_construct_with_all_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        event = CanonicalEvent(
            event_id="evt-003",
            patient_key="patient-789",
            event_type="ADMIT",
            event_ts=now,
            source_system="adt_vendor_x",
            source_record_id="src-003",
            facility_raw="Good Samaritan Hospital",
            facility_canonical_id="FAC_001",
            admit_flag=True,
            discharge_flag=False,
            auth_flag=False,
            patient_class="inpatient",
            drg="470",
            principal_diagnosis="J18.9",
            diagnosis_codes=[{"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"}],
            auth_status="approved",
            payer_id="PAYER-001",
            ingested_at=now,
            batch_id="batch-002",
            _raw_payload={"hl7_event": "A01", "patient_id": "789"},
        )
        assert event.facility_canonical_id == "FAC_001"
        assert event.admit_flag is True
        assert event.discharge_flag is False
        assert event.auth_flag is False
        assert event.patient_class == "inpatient"
        assert event.drg == "470"
        assert event.principal_diagnosis == "J18.9"
        assert event.diagnosis_codes == [{"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"}]
        assert event.auth_status == "approved"
        assert event.payer_id == "PAYER-001"
        assert event._raw_payload == {"hl7_event": "A01", "patient_id": "789"}

    def test_field_types(self) -> None:
        now = datetime.now(tz=timezone.utc)
        event = CanonicalEvent(
            event_id="evt-004",
            patient_key="patient-000",
            event_type="TRANSFER_IN",
            event_ts=now,
            source_system="adt",
            source_record_id="src-004",
            facility_raw="Test Facility",
            ingested_at=now,
            batch_id="batch-003",
        )
        assert isinstance(event.event_id, str)
        assert isinstance(event.patient_key, str)
        assert isinstance(event.event_type, str)
        assert isinstance(event.event_ts, datetime)
        assert isinstance(event.source_system, str)
        assert isinstance(event.source_record_id, str)
        assert isinstance(event.facility_raw, str)
        assert isinstance(event.ingested_at, datetime)
        assert isinstance(event.batch_id, str)

    def test_importable_from_models(self) -> None:
        """Verify the import path works as specified in acceptance criteria."""
        from asre.models.canonical_event import CanonicalEvent as CE
        assert CE is CanonicalEvent
