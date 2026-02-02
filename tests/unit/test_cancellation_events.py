"""Tests for US-049: Handle cancellation events.

CANCEL_ADMIT marks encounter status = cancelled.
CANCEL_DISCHARGE removes discharge, sets status back to open (encounter reopened).
Cancel events attach to the most recent matching encounter for patient at facility.
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import EncounterStitcher, StitchedEncounter


def _make_event(
    event_type: str,
    event_ts: datetime,
    patient_key: str = "PAT-001",
    facility_canonical_id: str | None = "FAC-001",
    source_system: str = "adt_vendor_x",
    patient_class: str | None = "inpatient",
) -> CanonicalEvent:
    """Helper to create a CanonicalEvent with minimal required fields."""
    return CanonicalEvent(
        event_id=f"evt-{event_type}-{event_ts.isoformat()}",
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts,
        source_system=source_system,
        source_record_id=f"src-{event_type}-{event_ts.isoformat()}",
        facility_raw="Test Hospital",
        facility_canonical_id=facility_canonical_id,
        ingested_at=datetime.now(tz=timezone.utc),
        batch_id="batch-001",
        patient_class=patient_class,
    )


class TestCancelAdmit:
    """CANCEL_ADMIT should mark the encounter status as cancelled."""

    def test_admit_then_cancel_admit_produces_cancelled_encounter(self) -> None:
        """ADMIT + CANCEL_ADMIT produces encounter with status=cancelled."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_ADMIT", datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].status == "cancelled"

    def test_cancel_admit_keeps_all_events(self) -> None:
        """Both ADMIT and CANCEL_ADMIT events are kept in the encounter."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_ADMIT", datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters[0].events) == 2
        event_types = [e.event_type for e in encounters[0].events]
        assert "ADMIT" in event_types
        assert "CANCEL_ADMIT" in event_types

    def test_cancel_admit_attaches_to_most_recent_encounter(self) -> None:
        """CANCEL_ADMIT attaches to the most recent encounter at the same facility."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc)),
            _make_event("DISCHARGE", datetime(2024, 1, 12, 10, 0, tzinfo=timezone.utc)),
            # Second encounter at same facility (new_encounter due to IP->IP)
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_ADMIT", datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        # First encounter: not cancelled
        assert encounters[0].status != "cancelled"
        # Second encounter: cancelled
        assert encounters[1].status == "cancelled"


class TestCancelDischarge:
    """CANCEL_DISCHARGE should remove discharge and reopen the encounter."""

    def test_admit_discharge_cancel_discharge_reopens_encounter(self) -> None:
        """ADMIT + DISCHARGE + CANCEL_DISCHARGE produces status=open, no discharge."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("DISCHARGE", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_DISCHARGE", datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].status == "open"

    def test_cancel_discharge_clears_has_discharge(self) -> None:
        """After CANCEL_DISCHARGE, has_discharge should be False."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("DISCHARGE", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_DISCHARGE", datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert encounters[0].has_discharge is False

    def test_cancel_discharge_keeps_all_events(self) -> None:
        """All three events (ADMIT, DISCHARGE, CANCEL_DISCHARGE) are in the encounter."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("DISCHARGE", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_DISCHARGE", datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters[0].events) == 3

    def test_cancel_discharge_attaches_to_encounter_with_discharge(self) -> None:
        """CANCEL_DISCHARGE goes to the most recent encounter at same facility."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("DISCHARGE", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc)),
            _make_event("CANCEL_DISCHARGE", datetime(2024, 1, 16, 14, 30, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].status == "open"


class TestCancellationMatchesFacility:
    """Cancel events should match to encounters at the same facility."""

    def test_cancel_admit_only_affects_same_facility(self) -> None:
        """CANCEL_ADMIT at facility A does not cancel encounter at facility B."""
        events = [
            _make_event(
                "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC-001",
            ),
            _make_event(
                "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC-002",
                patient_key="PAT-002",
            ),
            _make_event(
                "CANCEL_ADMIT",
                datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
                facility_canonical_id="FAC-001",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        # Find encounters per patient
        pat1_encounters = [e for e in encounters if e.patient_key == "PAT-001"]
        pat2_encounters = [e for e in encounters if e.patient_key == "PAT-002"]

        assert len(pat1_encounters) == 1
        assert pat1_encounters[0].status == "cancelled"
        assert len(pat2_encounters) == 1
        assert pat2_encounters[0].status != "cancelled"


class TestDefaultStatus:
    """Encounters without cancellation should have proper default status."""

    def test_admit_only_has_open_status(self) -> None:
        """An encounter with only an ADMIT event has status=open."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].status == "open"

    def test_admit_discharge_has_closed_status(self) -> None:
        """An encounter with ADMIT + DISCHARGE has status=closed."""
        events = [
            _make_event("ADMIT", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
            _make_event("DISCHARGE", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc)),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].status == "closed"
