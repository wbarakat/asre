"""Tests for StitchStage canonical history loading."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext
from asre.stitch.stage import StitchStage


def _make_event(event_id: str) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=event_id,
        patient_key="P001",
        event_type="ADMIT",
        event_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id=event_id,
        facility_raw="Test Hospital",
        facility_canonical_id="FAC_001",
        ingested_at=datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc),
        batch_id="batch_001",
        patient_class="inpatient",
    )


def _make_event_at(event_id: str, event_ts: datetime) -> CanonicalEvent:
    event = _make_event(event_id)
    event.event_ts = event_ts
    return event


def test_incremental_loads_history_events() -> None:
    adapter = MagicMock()
    context = PipelineContext(
        run_id="run_001",
        config={
            "adapter": adapter,
            "encounter_stitching": {
                "use_canonical_history": True,
                "history_lookback_days": 90,
            },
        },
        mode="incremental",
    )

    batch = EventBatch(batch_id="batch_001", events=[_make_event("evt-001")])

    history_event = _make_event("evt-002")

    with patch("asre.stitch.stage.CanonicalEventStore") as store_cls:
        store = store_cls.return_value
        store.fetch_recent_events.return_value = [history_event]
        store.ensure_table.return_value = None

        stage = StitchStage()
        stage.run(batch, context)

        store.fetch_recent_events.assert_called_once()
        assert stage.metrics.records_in == 2


def test_incremental_reuses_existing_encounter_id() -> None:
    adapter = MagicMock()
    existing = {
        "encounter_id": "enc_existing",
        "patient_key": "P001",
        "facility_canonical_id": "FAC_001",
        "admit_ts": "2026-01-01T10:00:00+00:00",
        "discharge_ts": "2026-01-02T10:00:00+00:00",
        "created_at": "2026-01-02T10:00:00+00:00",
        "updated_at": "2026-01-02T10:00:00+00:00",
        "status": "closed",
    }
    adapter.read_source.return_value = [existing]

    context = PipelineContext(
        run_id="run_001",
        config={
            "adapter": adapter,
            "encounter_stitching": {
                "use_canonical_history": True,
                "history_lookback_days": 90,
                "time_window_hours": 48,
                "facility_must_match": True,
            },
        },
        mode="incremental",
    )

    event_ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    batch = EventBatch(batch_id="batch_001", events=[_make_event_at("evt-003", event_ts)])

    with patch("asre.stitch.stage.CanonicalEventStore") as store_cls:
        store = store_cls.return_value
        store.fetch_recent_events.return_value = []
        store.ensure_table.return_value = None

        stage = StitchStage()
        stage.run(batch, context)

        assert stage.encounters[0].encounter_id == "enc_existing"


def test_full_run_does_not_reuse_existing_encounter_id() -> None:
    adapter = MagicMock()
    adapter.read_source.return_value = [
        {
            "encounter_id": "enc_existing",
            "patient_key": "P001",
            "facility_canonical_id": "FAC_001",
            "admit_ts": "2026-01-01T10:00:00+00:00",
            "discharge_ts": "2026-01-02T10:00:00+00:00",
            "created_at": "2026-01-02T10:00:00+00:00",
            "updated_at": "2026-01-02T10:00:00+00:00",
            "status": "closed",
        }
    ]

    context = PipelineContext(
        run_id="run_001",
        config={
            "adapter": adapter,
            "encounter_stitching": {
                "use_canonical_history": True,
                "history_lookback_days": 90,
                "time_window_hours": 48,
                "facility_must_match": True,
            },
        },
        mode="full",
    )

    event_ts = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    batch = EventBatch(batch_id="batch_001", events=[_make_event_at("evt-004", event_ts)])

    with patch("asre.stitch.stage.CanonicalEventStore") as store_cls:
        store = store_cls.return_value
        store.fetch_recent_events.return_value = []
        store.ensure_table.return_value = None

        stage = StitchStage()
        stage.run(batch, context)

        assert stage.encounters[0].encounter_id != "enc_existing"
