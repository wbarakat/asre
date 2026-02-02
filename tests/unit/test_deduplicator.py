"""Tests for the Deduplicator class (US-053).

Tests that duplicate events within encounters are identified based on
match_fields + time_tolerance_minutes.
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
        ingested_at=now,
        batch_id="batch-001",
        facility_canonical_id=facility_canonical_id,
    )


class TestDeduplicatorIdentification:
    """Test duplicate event identification within encounters."""

    def test_two_admit_events_15_min_apart_are_duplicates(self) -> None:
        """Two ADMIT events 15 minutes apart at same facility are duplicates."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_ts=base_ts + timedelta(minutes=15),
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        # Should find one group of duplicates containing both events
        assert len(groups) == 1
        assert len(groups[0]) == 2
        event_ids = {e.event_id for e in groups[0]}
        assert event_ids == {"evt-001", "evt-002"}

    def test_two_admit_events_45_min_apart_are_not_duplicates(self) -> None:
        """Two ADMIT events 45 minutes apart at same facility are NOT duplicates."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_ts=base_ts + timedelta(minutes=45),
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        # No duplicates found
        assert len(groups) == 0

    def test_admit_and_discharge_15_min_apart_are_not_duplicates(self) -> None:
        """ADMIT and DISCHARGE 15 minutes apart are NOT duplicates (different event_type)."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_type="ADMIT",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_type="DISCHARGE",
                event_ts=base_ts + timedelta(minutes=15),
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        assert len(groups) == 0

    def test_default_match_fields(self) -> None:
        """Default match fields are patient_key, event_type, facility_canonical_id."""
        dedup = Deduplicator()
        assert dedup.match_fields == [
            "patient_key",
            "event_type",
            "facility_canonical_id",
        ]

    def test_default_time_tolerance(self) -> None:
        """Default time tolerance is 30 minutes."""
        dedup = Deduplicator()
        assert dedup.time_tolerance_minutes == 30

    def test_custom_match_fields(self) -> None:
        """Custom match fields can be specified."""
        dedup = Deduplicator(
            match_fields=["patient_key", "event_type"],
            time_tolerance_minutes=60,
        )
        assert dedup.match_fields == ["patient_key", "event_type"]
        assert dedup.time_tolerance_minutes == 60

    def test_events_at_different_facilities_are_not_duplicates(self) -> None:
        """Events at different facilities are NOT duplicates even if within time window."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_ts=base_ts,
                facility_canonical_id="FAC-001",
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_ts=base_ts + timedelta(minutes=10),
                facility_canonical_id="FAC-002",
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        assert len(groups) == 0

    def test_events_exactly_at_tolerance_boundary_are_duplicates(self) -> None:
        """Events exactly 30 minutes apart (at boundary) are duplicates."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_ts=base_ts + timedelta(minutes=30),
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        assert len(groups) == 1

    def test_three_duplicates_form_single_group(self) -> None:
        """Three events matching on fields within time window form one group."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_ts=base_ts + timedelta(minutes=10),
                source_record_id="SRC-002",
            ),
            _make_event(
                event_id="evt-003",
                event_ts=base_ts + timedelta(minutes=20),
                source_record_id="SRC-003",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_no_events_returns_empty(self) -> None:
        """Empty event list returns no duplicate groups."""
        dedup = Deduplicator()
        groups = dedup.find_duplicates([])
        assert len(groups) == 0

    def test_single_event_returns_empty(self) -> None:
        """Single event cannot be a duplicate."""
        events = [_make_event()]
        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)
        assert len(groups) == 0

    def test_custom_time_tolerance(self) -> None:
        """Custom time tolerance of 60 minutes catches events 45 min apart."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                event_ts=base_ts + timedelta(minutes=45),
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator(time_tolerance_minutes=60)
        groups = dedup.find_duplicates(events)

        assert len(groups) == 1

    def test_different_patient_keys_not_duplicates(self) -> None:
        """Events with different patient_key are not duplicates."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event(
                event_id="evt-001",
                patient_key="PAT-001",
                event_ts=base_ts,
                source_record_id="SRC-001",
            ),
            _make_event(
                event_id="evt-002",
                patient_key="PAT-002",
                event_ts=base_ts + timedelta(minutes=5),
                source_record_id="SRC-002",
            ),
        ]

        dedup = Deduplicator()
        groups = dedup.find_duplicates(events)

        assert len(groups) == 0
