"""Tests for marking duplicates for audit (US-055).

Duplicate events are NOT deleted -- they remain in the event list.
Duplicate events have role_in_encounter = 'duplicate'.
The kept event retains its original role (admit_anchor, discharge_anchor, supporting).
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
    role_in_encounter: str | None = None,
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
        role_in_encounter=role_in_encounter,
    )


class TestMarkDuplicatesForAudit:
    """After dedup, duplicate events have role='duplicate', kept event has original role."""

    def test_duplicate_events_get_duplicate_role(self) -> None:
        """Duplicate events should have role_in_encounter = 'duplicate'."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        adt_event = _make_event(
            event_id="evt-adt",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-ADT",
            ingested_at=ingested,
            role_in_encounter="admit_anchor",
        )
        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
            role_in_encounter="supporting",
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([adt_event, claims_event])
        assert len(groups) == 1

        kept, duplicates = dedup.resolve_duplicates(groups, priority)

        # Mark roles
        dedup.mark_roles(kept, duplicates)

        # Kept event retains its original role
        assert kept[0].role_in_encounter == "admit_anchor"
        # Duplicate event gets 'duplicate' role
        assert duplicates[0].role_in_encounter == "duplicate"

    def test_kept_event_retains_supporting_role(self) -> None:
        """Kept event should retain its existing role (supporting)."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        adt_event = _make_event(
            event_id="evt-adt",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-ADT",
            ingested_at=ingested,
            role_in_encounter="supporting",
        )
        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
            role_in_encounter="supporting",
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([adt_event, claims_event])

        kept, duplicates = dedup.resolve_duplicates(groups, priority)
        dedup.mark_roles(kept, duplicates)

        assert kept[0].role_in_encounter == "supporting"
        assert duplicates[0].role_in_encounter == "duplicate"

    def test_kept_event_with_no_prior_role_keeps_none(self) -> None:
        """Kept event with no prior role_in_encounter stays None (assigned later)."""
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

        kept, duplicates = dedup.resolve_duplicates(groups, priority)
        dedup.mark_roles(kept, duplicates)

        # Kept event had no role, so it stays None
        assert kept[0].role_in_encounter is None
        # Duplicate always gets 'duplicate'
        assert duplicates[0].role_in_encounter == "duplicate"

    def test_multiple_duplicates_all_marked(self) -> None:
        """Three-way duplicate: two duplicates both get 'duplicate' role."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        adt_event = _make_event(
            event_id="evt-adt",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-ADT",
            ingested_at=ingested,
            role_in_encounter="admit_anchor",
        )
        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts + timedelta(minutes=5),
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
            role_in_encounter="supporting",
        )
        auth_event = _make_event(
            event_id="evt-auth",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="auth_portal",
            source_record_id="SRC-AUTH",
            ingested_at=ingested,
            role_in_encounter="supporting",
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([adt_event, claims_event, auth_event])

        kept, duplicates = dedup.resolve_duplicates(groups, priority)
        dedup.mark_roles(kept, duplicates)

        assert len(kept) == 1
        assert kept[0].role_in_encounter == "admit_anchor"
        assert len(duplicates) == 2
        assert all(d.role_in_encounter == "duplicate" for d in duplicates)

    def test_no_duplicates_no_role_changes(self) -> None:
        """When there are no duplicates, mark_roles does nothing."""
        dedup = Deduplicator()
        dedup.mark_roles([], [])
        # No error, nothing to assert beyond no exception

    def test_duplicate_events_remain_in_encounter(self) -> None:
        """Duplicate events are NOT deleted -- both kept and duplicates accessible."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        ingested = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)

        adt_event = _make_event(
            event_id="evt-adt",
            event_ts=base_ts,
            source_system="adt_vendor_x",
            source_record_id="SRC-ADT",
            ingested_at=ingested,
            role_in_encounter="admit_anchor",
        )
        claims_event = _make_event(
            event_id="evt-claims",
            event_ts=base_ts + timedelta(minutes=10),
            source_system="claims_clearinghouse",
            source_record_id="SRC-CLAIMS",
            ingested_at=ingested,
            role_in_encounter="supporting",
        )

        priority = {"adt": 100, "claims": 80, "auth": 40}
        dedup = Deduplicator()
        groups = dedup.find_duplicates([adt_event, claims_event])
        kept, duplicates = dedup.resolve_duplicates(groups, priority)
        dedup.mark_roles(kept, duplicates)

        # Both events still exist -- duplicates are retained for audit
        all_events = kept + duplicates
        assert len(all_events) == 2
        event_ids = {e.event_id for e in all_events}
        assert event_ids == {"evt-adt", "evt-claims"}
