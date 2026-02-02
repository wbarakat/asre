"""Tests for StitchStage (US-052).

StitchStage plugs into the pipeline runner, processing EventBatch of canonical
events and producing encounters. Tracks stage metrics: events_in, encounters_out,
transfers_detected, cancellations_processed.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.stitch.stage import StitchStage


def _make_event(
    event_id: str,
    patient_key: str,
    event_type: str,
    event_ts: datetime,
    source_system: str = "adt_vendor_x",
    source_record_id: str | None = None,
    facility_raw: str = "Hospital A",
    facility_canonical_id: str | None = "FAC_001",
    patient_class: str | None = None,
) -> CanonicalEvent:
    """Helper to create a CanonicalEvent for testing."""
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts,
        source_system=source_system,
        source_record_id=source_record_id or event_id,
        facility_raw=facility_raw,
        facility_canonical_id=facility_canonical_id,
        patient_class=patient_class,
        ingested_at=datetime.now(tz=timezone.utc),
        batch_id="batch-001",
    )


def _make_context() -> PipelineContext:
    """Helper to create a PipelineContext for testing."""
    return PipelineContext(
        run_id="run_20240115_100000",
        config={
            "encounter_stitching": {
                "time_window_hours": 48,
                "facility_must_match": True,
                "same_timestamp_tiebreaker": ["claims", "adt", "auth"],
                "patient_class_transitions": [
                    {"from": "ed", "to": "inpatient", "action": "merge"},
                    {"from": "observation", "to": "inpatient", "action": "merge"},
                    {"from": "inpatient", "to": "inpatient", "action": "new_encounter"},
                ],
            },
        },
        mode="full",
    )


# --- Interface Tests ---


class TestStitchStageInterface:
    """Verify StitchStage implements PipelineStage correctly."""

    def test_is_pipeline_stage_subclass(self) -> None:
        assert issubclass(StitchStage, PipelineStage)

    def test_has_run_method(self) -> None:
        stage = StitchStage()
        assert hasattr(stage, "run")
        assert callable(stage.run)

    def test_run_returns_event_batch(self) -> None:
        stage = StitchStage()
        batch = EventBatch(batch_id="b1", events=[])
        result = stage.run(batch, _make_context())
        assert isinstance(result, EventBatch)


# --- Basic Processing Tests ---


class TestStitchStageProcessing:
    """Verify StitchStage processes events into encounters."""

    def test_empty_batch_produces_no_encounters(self) -> None:
        stage = StitchStage()
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())
        assert stage.encounters == []

    def test_single_admit_produces_one_encounter(self) -> None:
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert len(stage.encounters) == 1

    def test_admit_discharge_same_encounter(self) -> None:
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "DISCHARGE",
                datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert len(stage.encounters) == 1

    def test_two_patients_produce_two_encounters(self) -> None:
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT2", "ADMIT",
                datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert len(stage.encounters) == 2

    def test_encounters_have_encounter_ids(self) -> None:
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert stage.encounters[0].encounter_id is not None
        assert len(stage.encounters[0].encounter_id) > 0

    def test_encounters_have_metadata(self) -> None:
        """StitchStage should also build metadata for each encounter."""
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                source_system="adt_vendor_x",
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "DISCHARGE",
                datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc),
                source_system="claims_clearinghouse",
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        # Metadata should be built alongside encounters
        assert len(stage.encounter_metadata) == 1
        meta = stage.encounter_metadata[0]
        assert meta.encounter_type == "inpatient"
        assert meta.has_adt is True
        assert meta.has_claims is True


# --- Stage Metrics Tests ---


class TestStitchStageMetrics:
    """Verify StitchStage records correct stage metrics."""

    def test_metrics_events_in(self) -> None:
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "DISCHARGE",
                datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert stage.metrics.records_in == 2

    def test_metrics_encounters_out(self) -> None:
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT2", "ADMIT",
                datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert stage.metrics.records_out == 2

    def test_metrics_transfers_detected(self) -> None:
        """Transfer chain detection should be tracked in metrics."""
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_001",
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "DISCHARGE",
                datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_001",
                patient_class="inpatient",
            ),
            _make_event(
                "e3", "PAT1", "ADMIT",
                datetime(2024, 1, 16, 12, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_002",
                facility_raw="Hospital B",
                patient_class="inpatient",
                source_record_id="src-e3",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert stage.transfers_detected == 1

    def test_metrics_cancellations_processed(self) -> None:
        """Cancellation events should be counted."""
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "CANCEL_ADMIT",
                datetime(2024, 1, 15, 11, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())
        assert stage.cancellations_processed == 1

    def test_metrics_stage_name(self) -> None:
        stage = StitchStage()
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())
        assert stage.metrics.stage_name == "stitch"

    def test_metrics_status_success(self) -> None:
        stage = StitchStage()
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())
        assert stage.metrics.status == "success"


# --- Config-Driven Tests ---


class TestStitchStageConfig:
    """Verify StitchStage reads config from PipelineContext."""

    def test_uses_config_time_window(self) -> None:
        """Events 72h apart should split with default 48h window but stitch with 100h."""
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "DISCHARGE",
                datetime(2024, 1, 18, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)

        # Default 48h window: 72h apart -> 2 encounters
        default_ctx = PipelineContext(run_id="run_1", config={}, mode="full")
        stage.run(batch, default_ctx)
        assert len(stage.encounters) == 2

        # Custom 100h window: 72h apart -> 1 encounter
        stage2 = StitchStage()
        context = PipelineContext(
            run_id="run_1",
            config={
                "encounter_stitching": {
                    "time_window_hours": 100,
                    "facility_must_match": True,
                },
            },
            mode="full",
        )
        stage2.run(batch, context)
        assert len(stage2.encounters) == 1

    def test_uses_default_config_when_missing(self) -> None:
        """StitchStage should work with empty/missing config."""
        stage = StitchStage()
        events = [
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                patient_class="inpatient",
            ),
        ]
        batch = EventBatch(batch_id="b1", events=events)
        context = PipelineContext(run_id="run_1", config={}, mode="full")
        stage.run(batch, context)
        assert len(stage.encounters) == 1


# --- Full End-to-End Test ---


class TestStitchStageEndToEnd:
    """Full batch processing end-to-end test."""

    def test_mixed_patients_facilities_transfers_cancellations(self) -> None:
        """Complex scenario with multiple patients, transfers, and cancellations."""
        events = [
            # Patient 1: admit at FAC_001, discharge, transfer to FAC_002
            _make_event(
                "e1", "PAT1", "ADMIT",
                datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_001",
                patient_class="inpatient",
            ),
            _make_event(
                "e2", "PAT1", "DISCHARGE",
                datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_001",
                patient_class="inpatient",
            ),
            _make_event(
                "e3", "PAT1", "ADMIT",
                datetime(2024, 1, 16, 12, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_002",
                facility_raw="Hospital B",
                patient_class="inpatient",
                source_record_id="src-e3",
            ),
            _make_event(
                "e4", "PAT1", "DISCHARGE",
                datetime(2024, 1, 17, 14, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_002",
                facility_raw="Hospital B",
                patient_class="inpatient",
            ),
            # Patient 2: admit then cancel
            _make_event(
                "e5", "PAT2", "ADMIT",
                datetime(2024, 1, 15, 8, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_001",
                patient_class="inpatient",
            ),
            _make_event(
                "e6", "PAT2", "CANCEL_ADMIT",
                datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_001",
                patient_class="inpatient",
            ),
            # Patient 3: simple admit + discharge (within 48h window)
            _make_event(
                "e7", "PAT3", "ADMIT",
                datetime(2024, 1, 16, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_003",
                facility_raw="Hospital C",
                patient_class="inpatient",
            ),
            _make_event(
                "e8", "PAT3", "DISCHARGE",
                datetime(2024, 1, 17, 10, 0, tzinfo=timezone.utc),
                facility_canonical_id="FAC_003",
                facility_raw="Hospital C",
                patient_class="inpatient",
            ),
        ]

        stage = StitchStage()
        batch = EventBatch(batch_id="b1", events=events)
        stage.run(batch, _make_context())

        # 4 encounters: PAT1 at FAC_001, PAT1 at FAC_002, PAT2 at FAC_001, PAT3 at FAC_003
        assert len(stage.encounters) == 4

        # Verify metrics
        assert stage.metrics.records_in == 8
        assert stage.metrics.records_out == 4
        assert stage.transfers_detected == 1
        assert stage.cancellations_processed == 1

        # All encounters should have IDs
        for enc in stage.encounters:
            assert enc.encounter_id is not None

        # Verify metadata built for all encounters
        assert len(stage.encounter_metadata) == 4
