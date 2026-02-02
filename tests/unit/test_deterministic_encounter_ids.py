"""Tests for US-050: Deterministic encounter IDs.

encounter_id = hash(patient_key + facility_canonical_id + first_admit_source_record_id)
Same inputs always produce same encounter_id (verified across runs).
Hash function produces a URL-safe string (SHA-256 hex digest, truncated).
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import EncounterStitcher, StitchedEncounter


def _make_event(
    patient_key: str = "PAT_001",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "SRC_001",
    facility_canonical_id: str | None = "FAC_001",
    patient_class: str | None = "inpatient",
    admit_flag: bool | None = True,
) -> CanonicalEvent:
    if event_ts is None:
        event_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
    return CanonicalEvent(
        event_id="evt-test",
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts,
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw="Test Hospital",
        ingested_at=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
        batch_id="batch-test",
        facility_canonical_id=facility_canonical_id,
        admit_flag=admit_flag,
        patient_class=patient_class,
    )


class TestDeterministicEncounterIds:
    """Test deterministic encounter_id generation."""

    def test_encounter_has_encounter_id(self) -> None:
        """StitchedEncounter should have an encounter_id field after stitching."""
        stitcher = EncounterStitcher()
        events = [_make_event()]
        encounters = stitcher.stitch(events)
        assert len(encounters) == 1
        assert encounters[0].encounter_id is not None
        assert isinstance(encounters[0].encounter_id, str)
        assert len(encounters[0].encounter_id) > 0

    def test_same_inputs_produce_same_id(self) -> None:
        """Same patient + facility + source_record_id should produce same encounter_id."""
        stitcher = EncounterStitcher()
        events1 = [_make_event(patient_key="PAT_A", facility_canonical_id="FAC_X", source_record_id="SRC_100")]
        events2 = [_make_event(patient_key="PAT_A", facility_canonical_id="FAC_X", source_record_id="SRC_100")]

        encounters1 = stitcher.stitch(events1)
        encounters2 = stitcher.stitch(events2)

        assert encounters1[0].encounter_id == encounters2[0].encounter_id

    def test_different_source_record_id_produces_different_id(self) -> None:
        """Different source_record_id should produce different encounter_id."""
        stitcher = EncounterStitcher()
        events1 = [_make_event(source_record_id="SRC_AAA")]
        events2 = [_make_event(source_record_id="SRC_BBB")]

        encounters1 = stitcher.stitch(events1)
        encounters2 = stitcher.stitch(events2)

        assert encounters1[0].encounter_id != encounters2[0].encounter_id

    def test_different_patient_key_produces_different_id(self) -> None:
        """Different patient_key should produce different encounter_id."""
        stitcher = EncounterStitcher()
        events1 = [_make_event(patient_key="PAT_A")]
        events2 = [_make_event(patient_key="PAT_B")]

        encounters1 = stitcher.stitch(events1)
        encounters2 = stitcher.stitch(events2)

        assert encounters1[0].encounter_id != encounters2[0].encounter_id

    def test_different_facility_produces_different_id(self) -> None:
        """Different facility_canonical_id should produce different encounter_id."""
        stitcher = EncounterStitcher()
        events1 = [_make_event(facility_canonical_id="FAC_A")]
        events2 = [_make_event(facility_canonical_id="FAC_B")]

        encounters1 = stitcher.stitch(events1)
        encounters2 = stitcher.stitch(events2)

        assert encounters1[0].encounter_id != encounters2[0].encounter_id

    def test_id_is_url_safe_hex_string(self) -> None:
        """Encounter ID should be a URL-safe hex digest string."""
        stitcher = EncounterStitcher()
        events = [_make_event()]
        encounters = stitcher.stitch(events)
        encounter_id = encounters[0].encounter_id
        # SHA-256 hex digest characters are 0-9 and a-f
        assert all(c in "0123456789abcdef" for c in encounter_id)

    def test_uses_first_admit_source_record_id(self) -> None:
        """When encounter has multiple events, use the first admit event's source_record_id."""
        stitcher = EncounterStitcher()
        admit_event = _make_event(
            event_type="ADMIT",
            source_record_id="FIRST_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            admit_flag=True,
        )
        discharge_event = _make_event(
            event_type="DISCHARGE",
            source_record_id="DISCHARGE_REC",
            event_ts=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
            admit_flag=None,
        )
        events = [admit_event, discharge_event]
        encounters = stitcher.stitch(events)

        # Also stitch just the admit event alone
        events_single = [_make_event(source_record_id="FIRST_ADMIT")]
        encounters_single = stitcher.stitch(events_single)

        assert encounters[0].encounter_id == encounters_single[0].encounter_id

    def test_null_facility_uses_empty_string_in_hash(self) -> None:
        """When facility_canonical_id is None, it should still produce a valid ID."""
        stitcher = EncounterStitcher(facility_must_match=False)
        events = [_make_event(facility_canonical_id=None)]
        encounters = stitcher.stitch(events)
        assert encounters[0].encounter_id is not None
        assert len(encounters[0].encounter_id) > 0

    def test_stable_across_repeated_stitching(self) -> None:
        """Running stitch multiple times with same data produces identical IDs."""
        stitcher = EncounterStitcher()
        events = [
            _make_event(
                event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                source_record_id="SRC_STABLE",
            ),
            _make_event(
                event_type="DISCHARGE",
                event_ts=datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc),
                source_record_id="SRC_STABLE_DISCH",
                admit_flag=None,
            ),
        ]

        ids = set()
        for _ in range(5):
            encounters = stitcher.stitch(events)
            ids.add(encounters[0].encounter_id)

        assert len(ids) == 1, f"Expected 1 unique ID across 5 runs, got {len(ids)}: {ids}"
