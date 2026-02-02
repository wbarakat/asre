"""Tests for paired event emission for claims sources (US-029)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asre.canonicalize.paired_event_emitter import PairedEventEmitter
from asre.config.source_schema import (
    FieldMappings,
    PairedEventConfig,
    PairedEvents,
)


@pytest.fixture
def field_mappings() -> FieldMappings:
    return FieldMappings(
        patient_key="member_id",
        event_ts="admission_date",
        source_record_id="claim_id",
        facility_raw="facility_name",
        payer_id="payer_code",
        drg="drg_code",
        principal_diagnosis="primary_dx",
    )


@pytest.fixture
def paired_events() -> PairedEvents:
    return PairedEvents(
        admit=PairedEventConfig(event_ts="admission_date", event_type="CLAIM_ADMIT"),
        discharge=PairedEventConfig(event_ts="discharge_date", event_type="CLAIM_DISCHARGE"),
    )


@pytest.fixture
def emitter(field_mappings: FieldMappings, paired_events: PairedEvents) -> PairedEventEmitter:
    return PairedEventEmitter(field_mappings=field_mappings, paired_events=paired_events)


@pytest.fixture
def claims_record() -> dict[str, object]:
    return {
        "claim_id": "CLM-001",
        "member_id": "PAT-100",
        "admission_date": "2024-01-15T10:00:00",
        "discharge_date": "2024-01-18T14:00:00",
        "facility_name": "General Hospital",
        "payer_code": "BCBS",
        "drg_code": "470",
        "primary_dx": "M17.11",
        "_raw_payload": {"claim_id": "CLM-001", "member_id": "PAT-100"},
    }


class TestPairedEventEmitterConstruction:
    def test_creates_emitter(
        self, field_mappings: FieldMappings, paired_events: PairedEvents
    ) -> None:
        emitter = PairedEventEmitter(field_mappings=field_mappings, paired_events=paired_events)
        assert emitter.field_mappings is field_mappings
        assert emitter.paired_events is paired_events


class TestPairedEventEmission:
    def test_one_row_produces_two_events(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert len(events) == 2

    def test_admit_event_type(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        admit = events[0]
        assert admit.event_type == "CLAIM_ADMIT"

    def test_discharge_event_type(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        discharge = events[1]
        assert discharge.event_type == "CLAIM_DISCHARGE"

    def test_admit_event_ts_uses_admit_column(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        admit = events[0]
        assert admit.event_ts == datetime.fromisoformat("2024-01-15T10:00:00")

    def test_discharge_event_ts_uses_discharge_column(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        discharge = events[1]
        assert discharge.event_ts == datetime.fromisoformat("2024-01-18T14:00:00")

    def test_admit_flag_set_on_admit_event(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].admit_flag is True

    def test_discharge_flag_set_on_discharge_event(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[1].discharge_flag is True

    def test_admit_flag_not_set_on_discharge(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[1].admit_flag is None

    def test_discharge_flag_not_set_on_admit(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].discharge_flag is None


class TestSharedFields:
    def test_both_share_source_record_id(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].source_record_id == "CLM-001"
        assert events[1].source_record_id == "CLM-001"

    def test_both_share_patient_key(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].patient_key == "PAT-100"
        assert events[1].patient_key == "PAT-100"

    def test_both_share_facility_raw(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].facility_raw == "General Hospital"
        assert events[1].facility_raw == "General Hospital"

    def test_both_share_source_system(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].source_system == "claims_clearinghouse"
        assert events[1].source_system == "claims_clearinghouse"

    def test_both_share_batch_id(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].batch_id == "batch-1"
        assert events[1].batch_id == "batch-1"

    def test_optional_fields_mapped_on_both(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        for event in events:
            assert event.payer_id == "BCBS"
            assert event.drg == "470"
            assert event.principal_diagnosis == "M17.11"


class TestUniqueEventIds:
    def test_each_event_has_unique_id(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        assert events[0].event_id != events[1].event_id

    def test_event_ids_are_uuids(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        import uuid

        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        for event in events:
            uuid.UUID(event.event_id)  # Raises ValueError if invalid


class TestRawPayload:
    def test_raw_payload_preserved_on_both(
        self, emitter: PairedEventEmitter, claims_record: dict[str, object]
    ) -> None:
        events = emitter.emit(claims_record, source_system="claims_clearinghouse", batch_id="batch-1")
        for event in events:
            assert event._raw_payload == {"claim_id": "CLM-001", "member_id": "PAT-100"}
