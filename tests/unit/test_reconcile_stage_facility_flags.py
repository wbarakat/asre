"""Tests for facility unresolved flagging in ReconcileStage."""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext
from asre.reconcile.stage import ReconcileStage
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(*, facility_id: str | None, match_type: str | None) -> CanonicalEvent:
    now = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    return CanonicalEvent(
        event_id="evt-1",
        patient_key="PAT-1",
        event_type="ADMIT",
        event_ts=now,
        source_system="adt_vendor_x",
        source_record_id="src-1",
        facility_raw="Test Facility",
        ingested_at=now,
        batch_id="batch-1",
        facility_canonical_id=facility_id,
        facility_match_type=match_type,
        patient_class="inpatient",
    )


def _make_encounter(events: list[CanonicalEvent]) -> StitchedEncounter:
    return StitchedEncounter(
        patient_key="PAT-1",
        facility_canonical_id=events[0].facility_canonical_id,
        events=events,
        last_event_ts=events[-1].event_ts,
        encounter_type=events[0].patient_class,
    )


class TestReconcileStageFacilityFlags:
    def test_flags_unresolved_when_match_type_new(self) -> None:
        stage = ReconcileStage()
        enc = _make_encounter([_make_event(facility_id="FAC_001", match_type="new")])
        stage.encounters_in = [enc]
        ctx = PipelineContext(run_id="run-1", config={}, mode="full")
        stage.run(EventBatch(batch_id="run-1", events=[]), ctx)

        flags = stage.encounters[0].confidence_flags
        assert "FACILITY_UNRESOLVED" in flags

    def test_flags_unresolved_when_facility_missing(self) -> None:
        stage = ReconcileStage()
        enc = _make_encounter([_make_event(facility_id=None, match_type=None)])
        stage.encounters_in = [enc]
        ctx = PipelineContext(run_id="run-1", config={}, mode="full")
        stage.run(EventBatch(batch_id="run-1", events=[]), ctx)

        flags = stage.encounters[0].confidence_flags
        assert "FACILITY_UNRESOLVED" in flags
