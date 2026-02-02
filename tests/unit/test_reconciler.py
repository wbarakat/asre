"""Tests for Reconciler — timestamp selection by source priority (US-058)."""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent
from asre.reconcile.reconciler import Reconciler
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    event_id: str,
    event_type: str,
    event_ts: datetime,
    source_system: str,
    patient_key: str = "PAT-001",
    source_record_id: str = "SRC-001",
    facility_raw: str = "Test Hospital",
    facility_canonical_id: str | None = "FAC-001",
    patient_class: str | None = None,
    admit_flag: bool | None = None,
    discharge_flag: bool | None = None,
) -> CanonicalEvent:
    """Helper to create canonical events for testing."""
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts,
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw=facility_raw,
        facility_canonical_id=facility_canonical_id,
        ingested_at=datetime(2024, 1, 20, 0, 0, tzinfo=timezone.utc),
        batch_id="batch-001",
        patient_class=patient_class,
        admit_flag=admit_flag,
        discharge_flag=discharge_flag,
    )


def _make_encounter(events: list[CanonicalEvent]) -> StitchedEncounter:
    """Helper to build a StitchedEncounter from events."""
    enc = StitchedEncounter(
        patient_key=events[0].patient_key,
        facility_canonical_id=events[0].facility_canonical_id,
    )
    for event in events:
        enc.add_event(event)
    enc.generate_encounter_id()
    return enc


class TestTimestampSelectionBySourcePriority:
    """US-058: admit_ts and discharge_ts selected from most trusted source."""

    def test_admit_ts_from_highest_priority_source(self) -> None:
        """ADT admit (priority 100) beats claims admit (priority 80)."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-003",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit, adt_discharge])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        # ADT has priority 100 > claims priority 80, so ADT's admit_ts is used
        assert result.admit_ts == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert result.admit_source_priority == "adt"

    def test_discharge_ts_from_highest_priority_source(self) -> None:
        """ADT discharge (priority 100) beats claims discharge (priority 80)."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_discharge = _make_event(
            event_id="evt-002",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 18, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-003",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_discharge, adt_discharge])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        # ADT discharge used (priority 100 > claims 80)
        assert result.discharge_ts == datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc)
        assert result.discharge_source_priority == "adt"

    def test_claims_used_when_no_adt(self) -> None:
        """When only claims source exists, claims timestamps are used."""
        claims_admit = _make_event(
            event_id="evt-001",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_discharge = _make_event(
            event_id="evt-002",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 18, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        enc = _make_encounter([claims_admit, claims_discharge])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        assert result.admit_ts == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert result.admit_source_priority == "claims"
        assert result.discharge_ts == datetime(2024, 1, 18, 15, 0, tzinfo=timezone.utc)
        assert result.discharge_source_priority == "claims"

    def test_custom_timestamp_priority(self) -> None:
        """Custom priority config is respected."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        # Reverse priority: claims > adt
        reconciler = Reconciler(
            timestamp_priority={"claims": 100, "adt": 80, "auth": 40}
        )
        result = reconciler.reconcile_timestamps(enc)

        # Claims should win with custom priority
        assert result.admit_ts == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert result.admit_source_priority == "claims"

    def test_open_encounter_no_discharge(self) -> None:
        """Open encounter has no discharge_ts and no discharge_source_priority."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        assert result.admit_ts == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert result.admit_source_priority == "adt"
        assert result.discharge_ts is None
        assert result.discharge_source_priority is None

    def test_auth_lowest_priority_for_timestamps(self) -> None:
        """Auth events have lowest timestamp priority (40 by default)."""
        auth_admit = _make_event(
            event_id="evt-001",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([auth_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        # Claims (80) > auth (40), so claims timestamp is used
        assert result.admit_ts == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert result.admit_source_priority == "claims"
