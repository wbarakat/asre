"""Tests for EncounterStitcher — US-043: Basic encounter stitching."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import EncounterStitcher


def _make_event(
    event_id: str = "evt-001",
    patient_key: str = "PAT-A",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "SRC-001",
    facility_canonical_id: str | None = "FAC-001",
    admit_flag: bool | None = None,
    discharge_flag: bool | None = None,
) -> CanonicalEvent:
    """Helper to create a CanonicalEvent with sensible defaults."""
    now = datetime.now(tz=timezone.utc)
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw="Test Facility",
        ingested_at=now,
        batch_id="batch-001",
        facility_canonical_id=facility_canonical_id,
        admit_flag=admit_flag,
        discharge_flag=discharge_flag,
    )


class TestEncounterStitcherConstruction:
    """Test EncounterStitcher can be constructed with config."""

    def test_default_construction(self) -> None:
        stitcher = EncounterStitcher()
        assert stitcher.time_window_hours == 48

    def test_custom_time_window(self) -> None:
        stitcher = EncounterStitcher(time_window_hours=24)
        assert stitcher.time_window_hours == 24

    def test_custom_tiebreaker(self) -> None:
        stitcher = EncounterStitcher(
            same_timestamp_tiebreaker=["adt", "claims", "auth"]
        )
        assert stitcher.same_timestamp_tiebreaker == ["adt", "claims", "auth"]


class TestPatientPartitioning:
    """Test events are partitioned by patient_key."""

    def test_single_patient_events(self) -> None:
        events = [
            _make_event(event_id="e1", patient_key="PAT-A"),
            _make_event(event_id="e2", patient_key="PAT-A"),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1

    def test_different_patients_separate_encounters(self) -> None:
        events = [
            _make_event(event_id="e1", patient_key="PAT-A"),
            _make_event(event_id="e2", patient_key="PAT-B"),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_three_patients_three_encounters(self) -> None:
        events = [
            _make_event(event_id="e1", patient_key="PAT-A"),
            _make_event(event_id="e2", patient_key="PAT-B"),
            _make_event(event_id="e3", patient_key="PAT-C"),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 3


class TestTimeSorting:
    """Test events are sorted by event_ts ascending within a patient."""

    def test_events_sorted_by_timestamp(self) -> None:
        """Events should be processed in chronological order."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=2),
                source_record_id="SRC-002",
            ),
            _make_event(
                event_id="e1",
                event_ts=base,
                source_record_id="SRC-001",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        # Both should be in same encounter (4h apart, within 48h window)
        assert len(encounters) == 1
        # Events should be ordered chronologically in the encounter
        enc = encounters[0]
        assert len(enc.events) == 2
        assert enc.events[0].event_id == "e1"
        assert enc.events[1].event_id == "e2"


class TestSameTimestampTiebreaker:
    """Test tiebreaker ordering for events with identical timestamps."""

    def test_default_tiebreaker_claims_first(self) -> None:
        """Default tiebreaker: claims > adt > auth."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                source_system="adt_vendor_x",
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base,
                source_system="claims_clearinghouse",
                source_record_id="SRC-002",
            ),
            _make_event(
                event_id="e3",
                event_ts=base,
                source_system="auth_portal",
                source_record_id="SRC-003",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        enc = encounters[0]
        # claims first, then adt, then auth
        assert enc.events[0].source_system == "claims_clearinghouse"
        assert enc.events[1].source_system == "adt_vendor_x"
        assert enc.events[2].source_system == "auth_portal"


class TestTimeWindowStitching:
    """Test time window-based encounter stitching."""

    def test_events_within_window_same_encounter(self) -> None:
        """Two ADT events 4 hours apart at same facility produce one encounter."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                source_record_id="SRC-001",
                admit_flag=True,
            ),
            _make_event(
                event_id="e2",
                event_type="DISCHARGE",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                discharge_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(time_window_hours=48)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1

    def test_events_outside_window_separate_encounters(self) -> None:
        """Two ADT events 72 hours apart at same facility produce two encounters."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=72),
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(time_window_hours=48)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_events_at_different_facilities_separate_encounters(self) -> None:
        """Two ADT events 4 hours apart at different facilities produce two encounters."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                facility_canonical_id="FAC-001",
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=4),
                facility_canonical_id="FAC-002",
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(time_window_hours=48)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_custom_time_window(self) -> None:
        """Events at 30h gap: within 48h window but outside 24h window."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=30),
                source_record_id="SRC-002",
            ),
        ]
        # With 24h window: two encounters
        stitcher_24h = EncounterStitcher(time_window_hours=24)
        encounters_24h = stitcher_24h.stitch(events)
        assert len(encounters_24h) == 2

        # With 48h window: one encounter
        stitcher_48h = EncounterStitcher(time_window_hours=48)
        encounters_48h = stitcher_48h.stitch(events)
        assert len(encounters_48h) == 1

    def test_time_window_relative_to_last_event(self) -> None:
        """Time window is measured from the last event in the encounter, not the first."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=40),
                source_record_id="SRC-002",
            ),
            _make_event(
                event_id="e3",
                event_ts=base + timedelta(hours=80),
                source_record_id="SRC-003",
            ),
        ]
        stitcher = EncounterStitcher(time_window_hours=48)
        encounters = stitcher.stitch(events)
        # e1 at 0h, e2 at 40h (within 48h of e1 -> same encounter)
        # e3 at 80h: 80h - 40h = 40h from e2 (within 48h of e2 -> same encounter)
        assert len(encounters) == 1

    def test_empty_events_produces_no_encounters(self) -> None:
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch([])
        assert len(encounters) == 0

    def test_single_event_produces_one_encounter(self) -> None:
        events = [_make_event(event_id="e1")]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 1


class TestEncounterOutput:
    """Test structure of returned encounter groupings."""

    def test_encounter_has_events_list(self) -> None:
        events = [_make_event(event_id="e1")]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert hasattr(encounters[0], "events")
        assert isinstance(encounters[0].events, list)

    def test_encounter_has_patient_key(self) -> None:
        events = [_make_event(event_id="e1", patient_key="PAT-X")]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert encounters[0].patient_key == "PAT-X"

    def test_encounter_has_facility(self) -> None:
        events = [
            _make_event(event_id="e1", facility_canonical_id="FAC-042")
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert encounters[0].facility_canonical_id == "FAC-042"

    def test_encounter_events_belong_to_correct_encounter(self) -> None:
        """Two patients, verify events are grouped correctly."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(event_id="e1", patient_key="PAT-A"),
            _make_event(event_id="e2", patient_key="PAT-B"),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        patient_map = {enc.patient_key: enc for enc in encounters}
        assert patient_map["PAT-A"].events[0].event_id == "e1"
        assert patient_map["PAT-B"].events[0].event_id == "e2"

    def test_encounter_tracks_last_event_ts(self) -> None:
        """Encounter should track the latest event timestamp for window computation."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(event_id="e1", event_ts=base, source_record_id="SRC-001"),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert encounters[0].last_event_ts == base + timedelta(hours=4)
