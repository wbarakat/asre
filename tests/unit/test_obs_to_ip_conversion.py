"""Tests for US-046: OBS to IP conversion.

OBS_START followed by OBS_TO_IP at the same facility within time window
should merge into a single encounter with obs_to_ip_conversion = true
and encounter_type = inpatient.
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


class TestObsToIpConversion:
    """Test OBS_START + OBS_TO_IP merge into single encounter with obs_to_ip_conversion flag."""

    def test_obs_start_then_obs_to_ip_produces_one_encounter(self) -> None:
        """OBS_START + OBS_TO_IP at same facility within time window produces one encounter."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="OBS_START",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="observation",
            ),
            _make_event(
                event_id="e2",
                event_type="OBS_TO_IP",
                event_ts=base + timedelta(hours=6),
                source_record_id="SRC-002",
                patient_class="inpatient",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 2

    def test_obs_to_ip_sets_obs_to_ip_conversion_flag(self) -> None:
        """Merged OBS+IP encounter should have obs_to_ip_conversion = true."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="OBS_START",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="observation",
            ),
            _make_event(
                event_id="e2",
                event_type="OBS_TO_IP",
                event_ts=base + timedelta(hours=6),
                source_record_id="SRC-002",
                patient_class="inpatient",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].obs_to_ip_conversion is True

    def test_obs_to_ip_encounter_type_is_inpatient(self) -> None:
        """Merged OBS+IP encounter should have encounter_type = inpatient."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="OBS_START",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="observation",
            ),
            _make_event(
                event_id="e2",
                event_type="OBS_TO_IP",
                event_ts=base + timedelta(hours=6),
                source_record_id="SRC-002",
                patient_class="inpatient",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].encounter_type == "inpatient"

    def test_obs_to_ip_based_on_patient_class_transitions(self) -> None:
        """Merge behavior is driven by patient_class_transitions config."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="OBS_START",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="observation",
            ),
            _make_event(
                event_id="e2",
                event_type="OBS_TO_IP",
                event_ts=base + timedelta(hours=6),
                source_record_id="SRC-002",
                patient_class="inpatient",
            ),
        ]
        # Default transitions include observation->inpatient merge
        stitcher = EncounterStitcher()
        transitions = stitcher.patient_class_transitions
        obs_to_ip = [
            t
            for t in transitions
            if t["from"] == "observation" and t["to"] == "inpatient"
        ]
        assert len(obs_to_ip) == 1
        assert obs_to_ip[0]["action"] == "merge"

    def test_obs_only_encounter_has_no_conversion_flag(self) -> None:
        """OBS_START + OBS_END without IP conversion should not set flag."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="OBS_START",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="observation",
            ),
            _make_event(
                event_id="e2",
                event_type="OBS_END",
                event_ts=base + timedelta(hours=12),
                source_record_id="SRC-002",
                patient_class="observation",
            ),
        ]
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].obs_to_ip_conversion is False
        assert encounters[0].encounter_type == "observation"

    def test_obs_to_ip_with_additional_events(self) -> None:
        """OBS_START + OBS_TO_IP + DISCHARGE should all merge, with conversion flag."""
        base = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="e1",
                event_type="OBS_START",
                event_ts=base,
                source_record_id="SRC-001",
                patient_class="observation",
            ),
            _make_event(
                event_id="e2",
                event_type="OBS_TO_IP",
                event_ts=base + timedelta(hours=6),
                source_record_id="SRC-002",
                patient_class="inpatient",
            ),
            _make_event(
                event_id="e3",
                event_type="DISCHARGE",
                event_ts=base + timedelta(hours=72),
                source_record_id="SRC-003",
                patient_class="inpatient",
                discharge_flag=True,
            ),
        ]
        stitcher = EncounterStitcher(time_window_hours=96)
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert len(encounters[0].events) == 3
        assert encounters[0].obs_to_ip_conversion is True
        assert encounters[0].encounter_type == "inpatient"

    def test_ed_to_ip_does_not_set_obs_conversion_flag(self) -> None:
        """ED->IP merge should NOT set obs_to_ip_conversion flag."""
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
        stitcher = EncounterStitcher()
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].obs_to_ip_conversion is False
