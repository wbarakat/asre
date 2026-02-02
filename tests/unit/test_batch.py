"""Tests for EventBatch dataclass."""

from datetime import datetime

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent


def _make_event(event_id: str = "evt-1") -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        patient_key="PAT-001",
        event_type="ADMIT",
        event_ts=datetime(2024, 1, 1, 10, 0),
        source_system="adt_vendor_x",
        source_record_id="SRC-001",
        facility_raw="St. Mary's Hospital",
        ingested_at=datetime(2024, 1, 1, 12, 0),
        batch_id="batch-001",
    )


def test_construction_with_events() -> None:
    events = [_make_event("evt-1"), _make_event("evt-2")]
    batch = EventBatch(batch_id="batch-001", events=events)

    assert batch.batch_id == "batch-001"
    assert len(batch.events) == 2
    assert batch.events[0].event_id == "evt-1"
    assert batch.events[1].event_id == "evt-2"


def test_construction_empty_events() -> None:
    batch = EventBatch(batch_id="batch-002", events=[])

    assert batch.batch_id == "batch-002"
    assert batch.events == []


def test_event_access_by_index() -> None:
    events = [_make_event("evt-1"), _make_event("evt-2"), _make_event("evt-3")]
    batch = EventBatch(batch_id="batch-003", events=events)

    assert batch.events[0].event_id == "evt-1"
    assert batch.events[2].event_id == "evt-3"


def test_event_iteration() -> None:
    events = [_make_event("evt-1"), _make_event("evt-2")]
    batch = EventBatch(batch_id="batch-004", events=events)

    ids = [e.event_id for e in batch.events]
    assert ids == ["evt-1", "evt-2"]


def test_batch_id_is_str() -> None:
    batch = EventBatch(batch_id="batch-005", events=[])
    assert isinstance(batch.batch_id, str)


def test_events_is_list_of_canonical_events() -> None:
    events = [_make_event()]
    batch = EventBatch(batch_id="batch-006", events=events)
    assert isinstance(batch.events, list)
    assert isinstance(batch.events[0], CanonicalEvent)
