"""Tests for encounter-level dedup (US-056).

Two encounters for same patient + same facility with overlapping time ranges
should merge into one. The merged encounter takes the earlier admit_ts and
later discharge_ts, combines all events, and uses the earlier encounter's ID.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from asre.dedup.deduplicator import Deduplicator
from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    event_id: str = "evt-001",
    patient_key: str = "PAT-123",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "SRC-001",
    facility_canonical_id: str | None = "FAC-001",
    ingested_at: datetime | None = None,
    patient_class: str | None = "inpatient",
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
        facility_raw="Test Hospital",
        ingested_at=ingested_at or now,
        batch_id="batch-001",
        facility_canonical_id=facility_canonical_id,
        patient_class=patient_class,
    )


def _make_encounter(
    patient_key: str,
    facility_canonical_id: str | None,
    events: list[CanonicalEvent],
    encounter_id: str | None = None,
) -> StitchedEncounter:
    """Build a StitchedEncounter from a list of events."""
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
    )
    for event in events:
        enc.add_event(event)
    if encounter_id is not None:
        enc.encounter_id = encounter_id
    else:
        enc.generate_encounter_id()
    return enc


class TestEncounterLevelDedup:
    """Merge overlapping encounters for the same patient at the same facility."""

    def test_overlapping_encounters_merge_into_one(self) -> None:
        """Two encounters at same patient+facility with overlapping time ranges merge."""
        # Encounter A: Jan 15 10:00 admit -> Jan 16 10:00 discharge
        evt_a1 = _make_event(
            event_id="evt-a1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            source_record_id="SRC-A1",
        )
        evt_a2 = _make_event(
            event_id="evt-a2",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            source_record_id="SRC-A2",
        )
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a1, evt_a2], encounter_id="enc-a")

        # Encounter B: Jan 15 14:00 admit -> Jan 17 10:00 discharge (overlaps with A)
        evt_b1 = _make_event(
            event_id="evt-b1",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            source_record_id="SRC-B1",
        )
        evt_b2 = _make_event(
            event_id="evt-b2",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 17, 10, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            source_record_id="SRC-B2",
        )
        enc_b = _make_encounter("PAT-123", "FAC-001", [evt_b1, evt_b2], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        assert len(merged) == 1
        assert len(merged[0].events) == 4
        # Uses the earlier encounter's ID (enc_a)
        assert merged[0].encounter_id == "enc-a"

    def test_non_overlapping_encounters_stay_separate(self) -> None:
        """Two encounters at same patient+facility with non-overlapping times stay separate."""
        # Encounter A: Jan 15 10:00 -> Jan 16 10:00
        evt_a1 = _make_event(
            event_id="evt-a1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-A1",
        )
        evt_a2 = _make_event(
            event_id="evt-a2",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-A2",
        )
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a1, evt_a2], encounter_id="enc-a")

        # Encounter B: Jan 20 10:00 -> Jan 21 10:00 (no overlap)
        evt_b1 = _make_event(
            event_id="evt-b1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-B1",
        )
        evt_b2 = _make_event(
            event_id="evt-b2",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 21, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-B2",
        )
        enc_b = _make_encounter("PAT-123", "FAC-001", [evt_b1, evt_b2], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        assert len(merged) == 2

    def test_different_facility_encounters_stay_separate(self) -> None:
        """Overlapping encounters at different facilities are NOT merged."""
        evt_a = _make_event(
            event_id="evt-a1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-A1",
            facility_canonical_id="FAC-001",
        )
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a], encounter_id="enc-a")

        evt_b = _make_event(
            event_id="evt-b1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            source_record_id="SRC-B1",
            facility_canonical_id="FAC-002",
        )
        enc_b = _make_encounter("PAT-123", "FAC-002", [evt_b], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        assert len(merged) == 2

    def test_different_patient_encounters_stay_separate(self) -> None:
        """Overlapping encounters for different patients are NOT merged."""
        evt_a = _make_event(
            event_id="evt-a1",
            patient_key="PAT-111",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-A1",
        )
        enc_a = _make_encounter("PAT-111", "FAC-001", [evt_a], encounter_id="enc-a")

        evt_b = _make_event(
            event_id="evt-b1",
            patient_key="PAT-222",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            source_record_id="SRC-B1",
        )
        enc_b = _make_encounter("PAT-222", "FAC-001", [evt_b], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        assert len(merged) == 2

    def test_merged_encounter_uses_earlier_encounter_id(self) -> None:
        """The merged encounter keeps the earlier encounter's ID for stability."""
        evt_a = _make_event(
            event_id="evt-a1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-A1",
        )
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a], encounter_id="enc-a")

        evt_b = _make_event(
            event_id="evt-b1",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc),
            source_record_id="SRC-B1",
            source_system="claims_clearinghouse",
        )
        enc_b = _make_encounter("PAT-123", "FAC-001", [evt_b], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        assert len(merged) == 1
        assert merged[0].encounter_id == "enc-a"

    def test_merged_encounter_combines_all_events(self) -> None:
        """The merged encounter contains all events from both encounters."""
        evt_a1 = _make_event(event_id="evt-a1", event_type="ADMIT",
                             event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                             source_record_id="SRC-A1")
        evt_a2 = _make_event(event_id="evt-a2", event_type="DISCHARGE",
                             event_ts=datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
                             source_record_id="SRC-A2")
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a1, evt_a2], encounter_id="enc-a")

        evt_b1 = _make_event(event_id="evt-b1", event_type="CLAIM_ADMIT",
                             event_ts=datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
                             source_system="claims_clearinghouse",
                             source_record_id="SRC-B1")
        enc_b = _make_encounter("PAT-123", "FAC-001", [evt_b1], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        assert len(merged) == 1
        event_ids = {e.event_id for e in merged[0].events}
        assert event_ids == {"evt-a1", "evt-a2", "evt-b1"}

    def test_open_encounters_overlap_with_later_admits(self) -> None:
        """An open encounter (no discharge) overlaps with any later encounter at same facility."""
        # Encounter A: Jan 15 10:00, open (no discharge)
        evt_a = _make_event(
            event_id="evt-a1",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_record_id="SRC-A1",
        )
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a], encounter_id="enc-a")

        # Encounter B: Jan 16 10:00, also at same facility
        evt_b = _make_event(
            event_id="evt-b1",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            source_record_id="SRC-B1",
        )
        enc_b = _make_encounter("PAT-123", "FAC-001", [evt_b], encounter_id="enc-b")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b])

        # Open encounter overlaps with any later one at same patient+facility
        assert len(merged) == 1
        assert merged[0].encounter_id == "enc-a"

    def test_three_overlapping_encounters_merge_into_one(self) -> None:
        """Three overlapping encounters should all merge into one (transitive)."""
        # A: Jan 15 10:00 -> Jan 16 10:00
        evt_a1 = _make_event(event_id="evt-a1", event_type="ADMIT",
                             event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                             source_record_id="SRC-A1")
        evt_a2 = _make_event(event_id="evt-a2", event_type="DISCHARGE",
                             event_ts=datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
                             source_record_id="SRC-A2")
        enc_a = _make_encounter("PAT-123", "FAC-001", [evt_a1, evt_a2], encounter_id="enc-a")

        # B: Jan 15 20:00 -> Jan 17 10:00 (overlaps A)
        evt_b1 = _make_event(event_id="evt-b1", event_type="CLAIM_ADMIT",
                             event_ts=datetime(2024, 1, 15, 20, 0, tzinfo=timezone.utc),
                             source_system="claims_clearinghouse",
                             source_record_id="SRC-B1")
        evt_b2 = _make_event(event_id="evt-b2", event_type="CLAIM_DISCHARGE",
                             event_ts=datetime(2024, 1, 17, 10, 0, tzinfo=timezone.utc),
                             source_system="claims_clearinghouse",
                             source_record_id="SRC-B2")
        enc_b = _make_encounter("PAT-123", "FAC-001", [evt_b1, evt_b2], encounter_id="enc-b")

        # C: Jan 16 20:00 -> Jan 18 10:00 (overlaps B, transitively overlaps A)
        evt_c1 = _make_event(event_id="evt-c1", event_type="ADMIT",
                             event_ts=datetime(2024, 1, 16, 20, 0, tzinfo=timezone.utc),
                             source_system="auth_portal",
                             source_record_id="SRC-C1")
        evt_c2 = _make_event(event_id="evt-c2", event_type="DISCHARGE",
                             event_ts=datetime(2024, 1, 18, 10, 0, tzinfo=timezone.utc),
                             source_system="auth_portal",
                             source_record_id="SRC-C2")
        enc_c = _make_encounter("PAT-123", "FAC-001", [evt_c1, evt_c2], encounter_id="enc-c")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc_a, enc_b, enc_c])

        assert len(merged) == 1
        assert len(merged[0].events) == 6
        assert merged[0].encounter_id == "enc-a"

    def test_empty_encounters_list(self) -> None:
        """Empty input returns empty output."""
        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([])
        assert merged == []

    def test_single_encounter_unchanged(self) -> None:
        """A single encounter is returned unchanged."""
        evt = _make_event(event_id="evt-1", source_record_id="SRC-1")
        enc = _make_encounter("PAT-123", "FAC-001", [evt], encounter_id="enc-1")

        dedup = Deduplicator()
        merged = dedup.merge_overlapping_encounters([enc])

        assert len(merged) == 1
        assert merged[0].encounter_id == "enc-1"
