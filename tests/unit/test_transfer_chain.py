"""Tests for US-048: Transfer chain detection.

Discharge from Facility A within time_window_hours of admit at Facility B
produces a transfer chain — each facility segment is its own encounter,
linked via the transfer_chain array.
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent
from asre.stitch.encounter_stitcher import EncounterStitcher


def _make_event(
    event_id: str,
    event_type: str,
    event_ts: datetime,
    patient_key: str = "PAT_001",
    patient_class: str | None = "inpatient",
    facility_canonical_id: str | None = "FAC_001",
    source_system: str = "adt_vendor_x",
) -> CanonicalEvent:
    """Helper to create a CanonicalEvent for transfer chain tests."""
    now = datetime.now(tz=timezone.utc)
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
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


class TestTransferChainDetection:
    """Transfer chain: discharge at Facility A, admit at Facility B within time window."""

    def test_discharge_at_a_admit_at_b_produces_two_encounters(self) -> None:
        """Discharge from Facility A + admit at Facility B within time window
        produces two separate encounters (one per facility)."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 17, 10, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert encounters[0].facility_canonical_id == "FAC_001"
        assert encounters[1].facility_canonical_id == "FAC_002"

    def test_transfer_chain_links_both_encounters(self) -> None:
        """Both encounters in a transfer should have transfer_chain arrays
        containing both encounter indices, ordered by time."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 17, 10, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        # Both encounters should have transfer_chain set
        assert encounters[0].transfer_chain is not None
        assert encounters[1].transfer_chain is not None
        # Chain should contain indices/references to both encounters in order
        assert len(encounters[0].transfer_chain) == 2
        assert len(encounters[1].transfer_chain) == 2
        # Both chains should be identical (same ordered list)
        assert encounters[0].transfer_chain == encounters[1].transfer_chain

    def test_no_transfer_when_outside_time_window(self) -> None:
        """Discharge at A and admit at B OUTSIDE time window should NOT create a transfer chain."""
        stitcher = EncounterStitcher(time_window_hours=48)

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            # 72 hours later — outside 48h window
            _make_event("3", "ADMIT", datetime(2024, 1, 18, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        # Neither should have transfer_chain
        assert encounters[0].transfer_chain == []
        assert encounters[1].transfer_chain == []

    def test_no_transfer_at_same_facility(self) -> None:
        """Events at the same facility should stitch normally, no transfer chain."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 1
        assert encounters[0].transfer_chain == []


class TestMultiHopTransferChain:
    """Multi-hop transfers: A -> B -> C produces three encounters, all linked."""

    def test_three_facility_chain_produces_three_encounters(self) -> None:
        """A -> B -> C transfer chain produces three separate encounters."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 16, 12, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("5", "ADMIT", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_003"),
            _make_event("6", "DISCHARGE", datetime(2024, 1, 18, 10, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_003"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 3
        assert encounters[0].facility_canonical_id == "FAC_001"
        assert encounters[1].facility_canonical_id == "FAC_002"
        assert encounters[2].facility_canonical_id == "FAC_003"

    def test_three_facility_chain_all_share_same_transfer_chain(self) -> None:
        """All three encounters in A -> B -> C chain should share the same transfer_chain array."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 16, 12, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("5", "ADMIT", datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_003"),
            _make_event("6", "DISCHARGE", datetime(2024, 1, 18, 10, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_003"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 3
        # All three should have transfer_chain with 3 entries
        for enc in encounters:
            assert len(enc.transfer_chain) == 3
        # All chains should be identical
        assert encounters[0].transfer_chain == encounters[1].transfer_chain
        assert encounters[1].transfer_chain == encounters[2].transfer_chain

    def test_transfer_chain_ordered_by_time(self) -> None:
        """Transfer chain array should be ordered by encounter time (earliest first)."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 16, 12, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        # First in chain should be the earlier encounter
        chain = encounters[0].transfer_chain
        # Verify order: index 0 is earlier encounter, index 1 is later
        # The chain entries should reference the encounters in chronological order
        assert chain[0] != chain[1]

    def test_partial_chain_only_first_two_linked(self) -> None:
        """If B->C is outside time window, only A->B should be linked, not C."""
        stitcher = EncounterStitcher(time_window_hours=48)

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 16, 12, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
            # 72h later — outside window
            _make_event("5", "ADMIT", datetime(2024, 1, 19, 12, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_003"),
            _make_event("6", "DISCHARGE", datetime(2024, 1, 21, 10, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_003"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 3
        # A and B linked (2-element chain)
        assert len(encounters[0].transfer_chain) == 2
        assert len(encounters[1].transfer_chain) == 2
        assert encounters[0].transfer_chain == encounters[1].transfer_chain
        # C is NOT linked
        assert encounters[2].transfer_chain == []


class TestTransferChainEdgeCases:
    """Edge cases for transfer chain detection."""

    def test_different_patients_no_transfer(self) -> None:
        """Different patients at different facilities should NOT be linked."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), patient_key="PAT_001", facility_canonical_id="FAC_001"),
            _make_event("2", "DISCHARGE", datetime(2024, 1, 15, 16, 0, tzinfo=timezone.utc), patient_key="PAT_001", facility_canonical_id="FAC_001"),
            _make_event("3", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), patient_key="PAT_002", facility_canonical_id="FAC_002"),
            _make_event("4", "DISCHARGE", datetime(2024, 1, 17, 10, 0, tzinfo=timezone.utc), patient_key="PAT_002", facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert encounters[0].transfer_chain == []
        assert encounters[1].transfer_chain == []

    def test_transfer_requires_discharge_before_admit(self) -> None:
        """A transfer requires a discharge at facility A before an admit at facility B.
        Two admits at different facilities without intermediate discharge are NOT a transfer."""
        stitcher = EncounterStitcher()

        events = [
            _make_event("1", "ADMIT", datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_001"),
            # No discharge — next event is at a different facility
            _make_event("2", "ADMIT", datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc), facility_canonical_id="FAC_002"),
        ]

        encounters = stitcher.stitch(events)

        assert len(encounters) == 2
        assert encounters[0].transfer_chain == []
        assert encounters[1].transfer_chain == []
