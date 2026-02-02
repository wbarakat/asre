"""Tests for US-044: Facility matching requirement for stitching."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


class TestFacilityMustMatchTrue:
    """When facility_must_match=true, events at different facilities create separate encounters."""

    def test_different_facilities_produce_separate_encounters(self) -> None:
        """Events at different facilities within time window produce separate encounters."""
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
        stitcher = EncounterStitcher(facility_must_match=True)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2
        assert encounters[0].facility_canonical_id == "FAC-001"
        assert encounters[1].facility_canonical_id == "FAC-002"

    def test_same_facility_same_encounter(self) -> None:
        """Events at same facility within time window produce one encounter."""
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
                facility_canonical_id="FAC-001",
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=True)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 2

    def test_default_is_facility_must_match_true(self) -> None:
        """Default construction should have facility_must_match=True."""
        stitcher = EncounterStitcher()
        assert stitcher.facility_must_match is True


class TestFacilityMustMatchFalse:
    """When facility_must_match=false, facility is ignored during stitching."""

    def test_different_facilities_same_encounter_when_false(self) -> None:
        """Events at different facilities within time window produce one encounter when facility_must_match=false."""
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
        stitcher = EncounterStitcher(facility_must_match=False)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 2

    def test_time_window_still_applies_when_facility_match_false(self) -> None:
        """Time window is still enforced even when facility matching is off."""
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
                event_ts=base + timedelta(hours=72),
                facility_canonical_id="FAC-002",
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=False, time_window_hours=48)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_null_facility_stitches_when_match_false(self) -> None:
        """Null facility events should stitch when facility_must_match=false."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                facility_canonical_id=None,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=4),
                facility_canonical_id=None,
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=False)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1

    def test_mixed_null_and_set_facilities_stitch_when_match_false(self) -> None:
        """Mix of null and set facilities should stitch when facility_must_match=false."""
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
                facility_canonical_id=None,
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=False)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1


class TestNullFacilityHandling:
    """Null facility_canonical_id is treated as non-matching when facility_must_match=true."""

    def test_null_facilities_do_not_auto_stitch(self) -> None:
        """Two events with null facility_canonical_id should NOT stitch together."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                facility_canonical_id=None,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=4),
                facility_canonical_id=None,
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=True)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_null_facility_and_set_facility_do_not_stitch(self) -> None:
        """Event with null facility and event with set facility should not stitch."""
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
                facility_canonical_id=None,
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=True)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_set_facility_and_null_facility_do_not_stitch(self) -> None:
        """Event with null facility followed by set facility should not stitch (reversed order)."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_ts=base,
                facility_canonical_id=None,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="e2",
                event_ts=base + timedelta(hours=4),
                facility_canonical_id="FAC-001",
                source_record_id="SRC-002",
            ),
        ]
        stitcher = EncounterStitcher(facility_must_match=True)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2
