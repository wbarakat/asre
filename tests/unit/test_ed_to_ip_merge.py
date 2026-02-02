"""Tests for US-045: ED to IP merge.

ED_ARRIVAL followed by inpatient ADMIT at the same facility within time window
should merge into a single encounter with encounter type = inpatient.
"""

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
    patient_class: str | None = None,
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
        patient_class=patient_class,
    )


class TestEdToIpMerge:
    """Test ED_ARRIVAL + ADMIT merge into single encounter."""

    def test_ed_arrival_then_admit_same_facility_produces_one_encounter(self) -> None:
        """ED_ARRIVAL at 10:00 + ADMIT at 14:00 same facility produces one encounter."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                patient_class="inpatient",
                admit_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ]
        )
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 2

    def test_ed_to_ip_merge_encounter_type_is_inpatient(self) -> None:
        """Merged ED+IP encounter should have encounter_type = inpatient."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                patient_class="inpatient",
                admit_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ]
        )
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        # encounter_type should be inpatient (IP takes precedence over ED)
        assert encounters[0].encounter_type == "inpatient"

    def test_ed_events_kept_in_encounter(self) -> None:
        """ED events should be preserved in the merged encounter."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                patient_class="inpatient",
                admit_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ]
        )
        encounters = stitcher.stitch(events)
        event_types = [e.event_type for e in encounters[0].events]
        assert "ED_ARRIVAL" in event_types
        assert "ADMIT" in event_types

    def test_ed_to_ip_merge_with_default_transitions(self) -> None:
        """Default patient_class_transitions should include ed->inpatient merge."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                patient_class="inpatient",
                admit_flag=True,
            ),
        ]
        # Default transitions should include ed->inpatient merge
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].encounter_type == "inpatient"

    def test_ed_to_ip_different_facility_separate_encounters(self) -> None:
        """ED at facility A + ADMIT at facility B should NOT merge."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
                facility_canonical_id="FAC-001",
            ),
            _make_event(
                event_id="e2",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                patient_class="inpatient",
                admit_flag=True,
                facility_canonical_id="FAC-002",
            ),
        ]
        stitcher = EncounterStitcher(
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ]
        )
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_ed_to_ip_outside_time_window_separate_encounters(self) -> None:
        """ED + ADMIT outside time window should NOT merge."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=72),
                source_record_id="SRC-002",
                patient_class="inpatient",
                admit_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(
            time_window_hours=48,
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ],
        )
        encounters = stitcher.stitch(events)
        assert len(encounters) == 2

    def test_ed_only_encounter_type_is_ed(self) -> None:
        """Encounter with only ED events should have encounter_type derived from patient_class."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ED_DEPARTURE",
                event_ts=base + timedelta(hours=4),
                source_record_id="SRC-002",
                patient_class="ed",
            ),
        ]
        stitcher = EncounterStitcher(
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ]
        )
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].encounter_type == "ed"

    def test_multiple_ed_events_before_admit_all_merge(self) -> None:
        """Multiple ED events followed by ADMIT should all merge into one encounter."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="ED_ARRIVAL",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="ed",
            ),
            _make_event(
                event_id="e2",
                event_type="ED_DEPARTURE",
                event_ts=base + timedelta(hours=2),
                source_record_id="SRC-002",
                patient_class="ed",
            ),
            _make_event(
                event_id="e3",
                event_type="ADMIT",
                event_ts=base + timedelta(hours=3),
                source_record_id="SRC-003",
                patient_class="inpatient",
                admit_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(
            patient_class_transitions=[
                {"from": "ed", "to": "inpatient", "action": "merge"},
            ]
        )
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 3
        assert encounters[0].encounter_type == "inpatient"
