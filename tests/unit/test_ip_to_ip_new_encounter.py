"""Tests for US-047: IP to IP as new encounter.

Same-day inpatient readmission at the same facility should create a new encounter,
not merge into the existing one. Based on patient_class_transitions:
  [{from: inpatient, to: inpatient, action: new_encounter}]
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import EncounterStitcher


def _make_event(
    event_id: str,
    event_type: str,
    event_ts: datetime,
    patient_class: str | None = None,
    facility_canonical_id: str | None = "FAC_001",
    source_system: str = "adt_vendor_x",
) -> CanonicalEvent:
    """Helper to create a CanonicalEvent for stitching tests."""
    now = datetime.now(tz=timezone.utc)
    return CanonicalEvent(
        event_id=event_id,
        patient_key="PAT_001",
        event_type=event_type,
        event_ts=event_ts,
        source_system=source_system,
        source_record_id=f"SRC_{event_id}",
        facility_raw="Test Hospital",
        facility_canonical_id=facility_canonical_id,
        ingested_at=now,
        batch_id="batch-001",
        patient_class=patient_class,
    )


class TestIPToIPNewEncounter:
    """IP discharge + new IP admit at same facility within time window -> two encounters."""

    def test_ip_discharge_then_ip_admit_produces_two_encounters(self) -> None:
        """Core requirement: DISCHARGE + ADMIT (both IP) at same facility within
        time window produces two separate encounters."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2

    def test_first_encounter_has_admit_and_discharge(self) -> None:
        """First encounter should contain the original admit + discharge."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert len(encounters[0].events) == 2
        assert encounters[0].events[0].event_type == "ADMIT"
        assert encounters[0].events[1].event_type == "DISCHARGE"

    def test_second_encounter_has_new_admit(self) -> None:
        """Second encounter should contain the new admit event."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert len(encounters[1].events) == 1
        assert encounters[1].events[0].event_type == "ADMIT"
        assert encounters[1].events[0].event_id == "3"

    def test_both_encounters_are_inpatient_type(self) -> None:
        """Both encounters should have encounter_type = inpatient."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert encounters[0].encounter_type == "inpatient"
        assert encounters[1].encounter_type == "inpatient"

    def test_ip_to_ip_default_transition_config(self) -> None:
        """The default patient_class_transitions should include IP->IP as new_encounter."""
        stitcher = EncounterStitcher()

        ip_to_ip = [
            t for t in stitcher.patient_class_transitions
            if t.get("from") == "inpatient" and t.get("to") == "inpatient"
        ]
        assert len(ip_to_ip) == 1
        assert ip_to_ip[0]["action"] == "new_encounter"

    def test_ed_to_ip_still_merges(self) -> None:
        """ED->IP should still merge (not be broken by IP->IP logic)."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ED_ARRIVAL", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="ed"),
            _make_event("2", "ADMIT", datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].encounter_type == "inpatient"

    def test_obs_to_ip_still_merges(self) -> None:
        """OBS->IP should still merge (not be broken by IP->IP logic)."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "OBS_START", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="observation"),
            _make_event("2", "OBS_TO_IP", datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 1

    def test_ip_to_ip_at_different_facility_also_two_encounters(self) -> None:
        """IP->IP at different facilities should also produce two encounters
        (facility mismatch AND transition rule both apply)."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="inpatient", facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), patient_class="inpatient", facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc), patient_class="inpatient", facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2

    def test_ip_discharge_then_ip_admit_with_supporting_events(self) -> None:
        """IP->IP with additional supporting events in the first encounter."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("2", "TRANSFER_IN", datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("3", "DISCHARGE", datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("4", "ADMIT", datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc), patient_class="inpatient"),
            _make_event("5", "DISCHARGE", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), patient_class="inpatient"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert len(encounters[0].events) == 3
        assert len(encounters[1].events) == 2
