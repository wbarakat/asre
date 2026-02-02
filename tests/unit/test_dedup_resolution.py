"""Tests for duplicate resolution by source priority (US-054).

When duplicates are found, the event from the highest timestamp_priority
source is kept. If same source, the earliest ingested record is kept.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from asre.dedup.deduplicator import Deduplicator
from asre.models.canonical_event import CanonicalEvent


def _make_event(
    event_id: str = "evt-001",
    patient_key: str = "PAT-123",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "SRC-001",
    facility_canonical_id: str | None = "FAC-001",
    ingested_at: datetime | None = None,
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
    )


class TestResolveDuplicatesBySourcePriority:
    """Test that duplicates are resolved by keeping highest-priority source."""

    def test_adt_kept_over_claims(self) -> None:
        """ADT event (priority 100) kept over claims event (priority 80)."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        adt_event = _make_event(
            event_id="evt-adt",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-ADT",
            ingested_at=ingested,
        )
        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([adt_event, claims_event])
        assert len(groups) == 1

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        assert len(kept) == 1
        assert len(duplicates) == 1
        assert kept[0].event_id == "evt-adt"
        assert duplicates[0].event_id == "evt-claims"

    def test_claims_kept_over_auth(self) -> None:
        """Claims event (priority 80) kept over auth event (priority 40)."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts,
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
        )
        auth_event = _make_event(
            event_id="evt-auth",
            event_ts=base_ts + timedelta(minutes=5),
            source_system="auth_portal",
            source_record_id="SRC-AUTH",
            ingested_at=ingested,
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([claims_event, auth_event])

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        assert len(kept) == 1
        assert kept[0].event_id == "evt-claims"
        assert duplicates[0].event_id == "evt-auth"

    def test_same_source_keeps_earlier_ingested(self) -> None:
        """Two ADT events: keep the one with earlier ingested_at."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        earlier_ingested = datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc)
        later_ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        event_early = _make_event(
            event_id="evt-early",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-001",
            ingested_at=earlier_ingested,
        )
        event_late = _make_event(
            event_id="evt-late",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="adt_vendor_x",
            source_record_id="SRC-002",
            ingested_at=later_ingested,
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([event_early, event_late])

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        assert len(kept) == 1
        assert kept[0].event_id == "evt-early"
        assert duplicates[0].event_id == "evt-late"

    def test_multiple_duplicate_groups_resolved_independently(self) -> None:
        """Each duplicate group is resolved independently."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        # Group 1: ADMIT duplicates
        admit_adt = _make_event(
            event_id="evt-admit-adt",
            event_type="ADMIT",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-A1",
            ingested_at=ingested,
        )
        admit_claims = _make_event(
            event_id="evt-admit-claims",
            event_type="ADMIT",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="claims_clearinghouse",
            source_record_id="SRC-A2",
            ingested_at=ingested,
        )

        # Group 2: DISCHARGE duplicates
        discharge_adt = _make_event(
            event_id="evt-disch-adt",
            event_type="DISCHARGE",
            event_ts=base_ts + timedelta(hours=24),
            source_system="adt_vendor_x",
            source_record_id="SRC-D1",
            ingested_at=ingested,
        )
        discharge_claims = _make_event(
            event_id="evt-disch-claims",
            event_type="DISCHARGE",
            event_ts=base_ts + timedelta(hours=24, minutes=15),
            source_system="claims_clearinghouse",
            source_record_id="SRC-D2",
            ingested_at=ingested,
        )

        all_events = [admit_adt, admit_claims, discharge_adt, discharge_claims]
        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates(all_events)

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        assert len(kept) == 2
        assert len(duplicates) == 2
        kept_ids = {e.event_id for e in kept}
        assert kept_ids == {"evt-admit-adt", "evt-disch-adt"}

    def test_three_way_duplicate_keeps_highest_priority(self) -> None:
        """Three-way duplicate: ADT > claims > auth."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        adt_event = _make_event(
            event_id="evt-adt",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-ADT",
            ingested_at=ingested,
        )
        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts + timedelta(minutes=5),
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
        )
        auth_event = _make_event(
            event_id="evt-auth",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="auth_portal",
            source_record_id="SRC-AUTH",
            ingested_at=ingested,
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([adt_event, claims_event, auth_event])

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        assert len(kept) == 1
        assert len(duplicates) == 2
        assert kept[0].event_id == "evt-adt"

    def test_unknown_source_gets_zero_priority(self) -> None:
        """Source not in priority map defaults to priority 0."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        known_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts,
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
        )
        unknown_event = _make_event(
            event_id="evt-unknown",
            event_ts=base_ts + timedelta(minutes=5),
            source_system="unknown_source",
            source_record_id="SRC-UNK",
            ingested_at=ingested,
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([known_event, unknown_event])

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        assert kept[0].event_id == "evt-claims"

    def test_empty_groups_returns_empty(self) -> None:
        """No duplicate groups means nothing to resolve."""
        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()

        kept, duplicates = dedup.resolve_duplicates([], priority)

        assert kept == []
        assert duplicates == []
