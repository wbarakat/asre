"""Tests for CanonicalEventStore persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from asre.canonicalize.store import CanonicalEventStore
from asre.models.canonical_event import CanonicalEvent


def _make_event(event_id: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        patient_key="P001",
        event_type="ADMIT",
        event_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="MSG-001",
        facility_raw="Test Hospital",
        ingested_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        batch_id="batch_001",
    )


def test_upsert_events_deletes_then_inserts() -> None:
    adapter = MagicMock()
    adapter.warehouse_type = "postgres"
    adapter.execute_ddl = MagicMock()
    adapter.write_records = MagicMock(return_value=1)

    store = CanonicalEventStore(adapter)
    store.upsert_events([_make_event("evt-001")])

    delete_calls = [
        c for c in adapter.execute_ddl.call_args_list
        if "DELETE FROM asre_canonical_events" in c[0][0]
    ]
    assert delete_calls
    adapter.write_records.assert_called_once()


def test_upsert_handles_datetime_in_raw_payload() -> None:
    adapter = MagicMock()
    adapter.warehouse_type = "postgres"
    adapter.execute_ddl = MagicMock()
    adapter.write_records = MagicMock(return_value=1)

    event = _make_event("evt-002")
    event._raw_payload = {"event_ts": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)}

    store = CanonicalEventStore(adapter)
    store.upsert_events([event])

    call_args = adapter.write_records.call_args
    assert call_args is not None
    record = call_args[0][1][0]
    assert isinstance(record["raw_payload"], str)
    assert "2026-01-01T10:00:00" in record["raw_payload"]
