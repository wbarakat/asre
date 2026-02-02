"""Tests for encounter metadata derivation (US-051).

Tests that StitchedEncounter metadata is correctly derived:
- encounter_type: inpatient > observation > ed_only > outpatient
- status: open, closed, cancelled
- admit_ts, discharge_ts, los_hours
- source_event_ids, source_systems
- has_adt, has_claims, has_auth
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import StitchedEncounter
from asre.stitch.metadata import EncounterMetadata, build_encounter_metadata


def _make_event(
    event_id: str = "evt-1",
    patient_key: str = "PAT-001",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "src-1",
    patient_class: str | None = "inpatient",
    facility_canonical_id: str | None = "FAC-001",
    admit_flag: bool | None = None,
    discharge_flag: bool | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts or datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw="Test Hospital",
        admit_flag=admit_flag,
        discharge_flag=discharge_flag,
        patient_class=patient_class,
        facility_canonical_id=facility_canonical_id,
        ingested_at=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        batch_id="batch-1",
    )


def _make_stitched_encounter(
    events: list[CanonicalEvent],
    patient_key: str = "PAT-001",
    facility_canonical_id: str | None = "FAC-001",
) -> StitchedEncounter:
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
    )
    for event in events:
        enc.add_event(event)
    enc.generate_encounter_id()
    return enc


class TestEncounterTypeDerivation:
    """encounter_type: inpatient if any IP event, observation if OBS but no IP,
    ed_only if only ED events, otherwise outpatient."""

    def test_inpatient_event_produces_inpatient(self) -> None:
        events = [
            _make_event(event_type="ADMIT", patient_class="inpatient"),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.encounter_type == "inpatient"

    def test_observation_without_ip_produces_observation(self) -> None:
        events = [
            _make_event(event_type="OBS_START", patient_class="observation"),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.encounter_type == "observation"

    def test_ed_only_produces_ed_only(self) -> None:
        events = [
            _make_event(event_type="ED_ARRIVAL", patient_class="ed"),
            _make_event(
                event_id="evt-2",
                event_type="ED_DEPARTURE",
                patient_class="ed",
                event_ts=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.encounter_type == "ed_only"

    def test_outpatient_produces_outpatient(self) -> None:
        events = [
            _make_event(event_type="ADMIT", patient_class="outpatient"),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.encounter_type == "outpatient"

    def test_mixed_ed_and_ip_produces_inpatient(self) -> None:
        """ED_ARRIVAL + ADMIT(IP) at same facility -> inpatient (IP takes precedence)."""
        events = [
            _make_event(event_type="ED_ARRIVAL", patient_class="ed"),
            _make_event(
                event_id="evt-2",
                event_type="ADMIT",
                patient_class="inpatient",
                event_ts=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.encounter_type == "inpatient"

    def test_no_patient_class_produces_outpatient(self) -> None:
        """Events with no patient_class default to outpatient."""
        events = [
            _make_event(event_type="ADMIT", patient_class=None),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.encounter_type == "outpatient"


class TestStatusDerivation:
    """status: open (no discharge), closed (has discharge), cancelled."""

    def test_open_no_discharge(self) -> None:
        events = [_make_event(event_type="ADMIT")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.status == "open"

    def test_closed_with_discharge(self) -> None:
        events = [
            _make_event(event_type="ADMIT"),
            _make_event(
                event_id="evt-2",
                event_type="DISCHARGE",
                event_ts=datetime(2025, 1, 3, 10, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.status == "closed"

    def test_cancelled(self) -> None:
        events = [
            _make_event(event_type="ADMIT"),
            _make_event(
                event_id="evt-2",
                event_type="CANCEL_ADMIT",
                event_ts=datetime(2025, 1, 1, 11, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.status == "cancelled"


class TestTimestampDerivation:
    """admit_ts, discharge_ts, los_hours."""

    def test_admit_ts_is_earliest_admit_event(self) -> None:
        events = [
            _make_event(
                event_type="ADMIT",
                event_ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                event_id="evt-2",
                event_type="CLAIM_ADMIT",
                event_ts=datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
                source_system="claims_clearinghouse",
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.admit_ts == datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)

    def test_discharge_ts_is_latest_discharge_event(self) -> None:
        events = [
            _make_event(
                event_type="ADMIT",
                event_ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                event_id="evt-2",
                event_type="DISCHARGE",
                event_ts=datetime(2025, 1, 3, 10, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
            _make_event(
                event_id="evt-3",
                event_type="CLAIM_DISCHARGE",
                event_ts=datetime(2025, 1, 3, 12, 0, tzinfo=timezone.utc),
                source_system="claims_clearinghouse",
                source_record_id="src-3",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.discharge_ts == datetime(2025, 1, 3, 12, 0, tzinfo=timezone.utc)

    def test_discharge_ts_null_when_open(self) -> None:
        events = [_make_event(event_type="ADMIT")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.discharge_ts is None

    def test_los_hours_computed(self) -> None:
        events = [
            _make_event(
                event_type="ADMIT",
                event_ts=datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                event_id="evt-2",
                event_type="DISCHARGE",
                event_ts=datetime(2025, 1, 3, 10, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.los_hours == 48.0

    def test_los_hours_null_when_open(self) -> None:
        events = [_make_event(event_type="ADMIT")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.los_hours is None

    def test_admit_ts_uses_arrival_events(self) -> None:
        """ED_ARRIVAL and OBS_START also count as admit/arrival events."""
        events = [
            _make_event(
                event_type="ED_ARRIVAL",
                patient_class="ed",
                event_ts=datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
            ),
            _make_event(
                event_id="evt-2",
                event_type="ADMIT",
                patient_class="inpatient",
                event_ts=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        # ED_ARRIVAL at 8:00 is earlier than ADMIT at 14:00
        assert meta.admit_ts == datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc)


class TestSourceDerivation:
    """source_event_ids, source_systems, has_adt, has_claims, has_auth."""

    def test_source_event_ids_lists_all_events(self) -> None:
        events = [
            _make_event(event_id="evt-1"),
            _make_event(event_id="evt-2", source_record_id="src-2"),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.source_event_ids == ["evt-1", "evt-2"]

    def test_source_systems_distinct(self) -> None:
        events = [
            _make_event(event_id="evt-1", source_system="adt_vendor_x"),
            _make_event(
                event_id="evt-2",
                source_system="adt_vendor_x",
                source_record_id="src-2",
            ),
            _make_event(
                event_id="evt-3",
                source_system="claims_clearinghouse",
                source_record_id="src-3",
                event_ts=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert sorted(meta.source_systems) == ["adt_vendor_x", "claims_clearinghouse"]

    def test_has_adt_true(self) -> None:
        events = [_make_event(source_system="adt_vendor_x")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.has_adt is True
        assert meta.has_claims is False
        assert meta.has_auth is False

    def test_has_claims_true(self) -> None:
        events = [_make_event(source_system="claims_clearinghouse")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.has_claims is True
        assert meta.has_adt is False

    def test_has_auth_true(self) -> None:
        events = [_make_event(source_system="auth_portal")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.has_auth is True
        assert meta.has_adt is False
        assert meta.has_claims is False

    def test_mixed_adt_and_claims(self) -> None:
        """PRD acceptance criteria: ADT admit + claims discharge -> has_adt=true, has_claims=true, has_auth=false."""
        events = [
            _make_event(
                event_id="evt-1",
                event_type="ADMIT",
                source_system="adt_vendor_x",
            ),
            _make_event(
                event_id="evt-2",
                event_type="CLAIM_DISCHARGE",
                source_system="claims_clearinghouse",
                source_record_id="src-2",
                event_ts=datetime(2025, 1, 3, 10, 0, tzinfo=timezone.utc),
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.has_adt is True
        assert meta.has_claims is True
        assert meta.has_auth is False
        assert meta.status == "closed"
        assert meta.encounter_type == "inpatient"


class TestObsToIpConversion:
    """obs_to_ip_conversion flag propagation."""

    def test_obs_to_ip_flag_set(self) -> None:
        events = [
            _make_event(event_type="OBS_START", patient_class="observation"),
            _make_event(
                event_id="evt-2",
                event_type="OBS_TO_IP",
                patient_class="inpatient",
                event_ts=datetime(2025, 1, 1, 14, 0, tzinfo=timezone.utc),
                source_record_id="src-2",
            ),
        ]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.obs_to_ip_conversion is True

    def test_no_obs_to_ip_flag(self) -> None:
        events = [_make_event(event_type="ADMIT")]
        enc = _make_stitched_encounter(events)
        meta = build_encounter_metadata(enc)
        assert meta.obs_to_ip_conversion is False
