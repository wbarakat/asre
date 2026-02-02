"""Tests for DedupStage (US-057).

DedupStage plugs into the pipeline runner, processing encounters and returning
deduplicated encounters. Tracks stage metrics: events_before, events_after,
duplicates_found, encounters_merged.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    event_id: str,
    patient_key: str,
    event_type: str,
    event_ts: datetime,
    source_system: str = "adt_vendor_x",
    source_record_id: str | None = None,
    facility_raw: str = "Hospital A",
    facility_canonical_id: str | None = "FAC_001",
    ingested_at: datetime | None = None,
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
        ingested_at=ingested_at or datetime.now(tz=timezone.utc),
        batch_id="batch-001",
    )


def _make_encounter(
    patient_key: str,
    facility_canonical_id: str | None,
    events: list[CanonicalEvent],
    encounter_id: str | None = None,
) -> StitchedEncounter:
    """Helper to create a StitchedEncounter with events."""
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
    )
    for event in events:
        enc.add_event(event)
    if encounter_id:
        enc.encounter_id = encounter_id
    else:
        enc.generate_encounter_id()
    return enc


def _make_context(
    source_priority: dict[str, int] | None = None,
    match_fields: list[str] | None = None,
    time_tolerance_minutes: int | None = None,
) -> PipelineContext:
    """Helper to create a PipelineContext for testing."""
    config: dict[str, object] = {}

    recon_config: dict[str, object] = {}
    if source_priority is not None:
        recon_config["timestamp_priority"] = source_priority
    if recon_config:
        config["reconciliation"] = recon_config

    dedup_config: dict[str, object] = {}
    if match_fields is not None:
        dedup_config["match_fields"] = match_fields
    if time_tolerance_minutes is not None:
        dedup_config["time_tolerance_minutes"] = time_tolerance_minutes
    if dedup_config:
        config["deduplication"] = dedup_config

    return PipelineContext(
        run_id="run_20240115_100000",
        config=config,
        mode="full",
    )


# --- Interface Tests ---


class TestDedupStageInterface:
    """Verify DedupStage implements PipelineStage correctly."""

    def test_is_pipeline_stage_subclass(self) -> None:
        from asre.dedup.stage import DedupStage

        assert issubclass(DedupStage, PipelineStage)

    def test_has_run_method(self) -> None:
        from asre.dedup.stage import DedupStage

        stage = DedupStage()
        assert hasattr(stage, "run")
        assert callable(stage.run)

    def test_run_returns_event_batch(self) -> None:
        from asre.dedup.stage import DedupStage

        stage = DedupStage()
        batch = EventBatch(batch_id="b1", events=[])
        result = stage.run(batch, _make_context())
        assert isinstance(result, EventBatch)


# --- Basic Processing Tests ---


class TestDedupStageProcessing:
    """Verify DedupStage processes encounters correctly."""

    def test_empty_encounters_produces_empty_result(self) -> None:
        from asre.dedup.stage import DedupStage

        stage = DedupStage()
        stage.encounters_in = []
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())
        assert stage.encounters == []

    def test_encounter_with_no_duplicates_passes_through(self) -> None:
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts),
            _make_event("e2", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events, encounter_id="ENC_001")

        stage = DedupStage()
        stage.encounters_in = [enc]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert len(stage.encounters) == 1
        assert len(stage.encounters[0].events) == 2

    def test_event_level_dedup_removes_duplicates(self) -> None:
        """Two ADMIT events 15 min apart at same facility should be deduped."""
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_system="adt_vendor_x",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e2", "PAT1", "ADMIT", ts + timedelta(minutes=15),
                        source_system="claims_clearinghouse",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e3", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events, encounter_id="ENC_001")

        stage = DedupStage()
        stage.encounters_in = [enc]
        context = _make_context(source_priority={"adt": 100, "claims": 80, "auth": 40})
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=context)

        # One encounter should remain
        assert len(stage.encounters) == 1
        # The kept event should be ADT (priority 100), duplicate is claims
        enc_out = stage.encounters[0]
        adt_events = [e for e in enc_out.events if e.source_system.startswith("adt")
                      and e.event_type == "ADMIT"]
        claims_events = [e for e in enc_out.events
                         if e.source_system.startswith("claims")
                         and e.event_type == "ADMIT"]
        # ADT kept, claims marked duplicate
        assert len(adt_events) == 1
        assert adt_events[0].role_in_encounter != "duplicate"
        assert len(claims_events) == 1
        assert claims_events[0].role_in_encounter == "duplicate"

    def test_encounter_level_dedup_merges_overlapping(self) -> None:
        """Two overlapping encounters for same patient+facility should merge."""
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        # Encounter 1: admit at 10:00, discharge at 20:00
        enc1_events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_record_id="src1"),
            _make_event("e2", "PAT1", "DISCHARGE", ts + timedelta(hours=10)),
        ]
        enc1 = _make_encounter("PAT1", "FAC_001", enc1_events, encounter_id="ENC_001")

        # Encounter 2: admit at 18:00 (overlaps with enc1's discharge at 20:00),
        # discharge at 30:00
        enc2_events = [
            _make_event("e3", "PAT1", "ADMIT", ts + timedelta(hours=8),
                        source_record_id="src3"),
            _make_event("e4", "PAT1", "DISCHARGE", ts + timedelta(hours=20)),
        ]
        enc2 = _make_encounter("PAT1", "FAC_001", enc2_events, encounter_id="ENC_002")

        stage = DedupStage()
        stage.encounters_in = [enc1, enc2]
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=_make_context())

        # Should merge to one encounter
        assert len(stage.encounters) == 1
        # Merged encounter should have all 4 events
        assert len(stage.encounters[0].events) == 4


# --- Stage Metrics Tests ---


class TestDedupStageMetrics:
    """Verify DedupStage records correct stage metrics."""

    def test_metrics_events_before(self) -> None:
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts),
            _make_event("e2", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events)

        stage = DedupStage()
        stage.encounters_in = [enc]
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=_make_context())

        assert stage.events_before == 2

    def test_metrics_events_after(self) -> None:
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_system="adt_vendor_x",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e2", "PAT1", "ADMIT", ts + timedelta(minutes=15),
                        source_system="claims_clearinghouse",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e3", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events)

        stage = DedupStage()
        stage.encounters_in = [enc]
        context = _make_context(source_priority={"adt": 100, "claims": 80, "auth": 40})
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=context)

        # 3 events total, 1 duplicate marked but still in list
        # events_after counts non-duplicate events
        assert stage.events_after == 2

    def test_metrics_duplicates_found(self) -> None:
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_system="adt_vendor_x",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e2", "PAT1", "ADMIT", ts + timedelta(minutes=15),
                        source_system="claims_clearinghouse",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e3", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events)

        stage = DedupStage()
        stage.encounters_in = [enc]
        context = _make_context(source_priority={"adt": 100, "claims": 80, "auth": 40})
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=context)

        assert stage.duplicates_found == 1

    def test_metrics_encounters_merged(self) -> None:
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        enc1_events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_record_id="src1"),
            _make_event("e2", "PAT1", "DISCHARGE", ts + timedelta(hours=10)),
        ]
        enc1 = _make_encounter("PAT1", "FAC_001", enc1_events, encounter_id="ENC_001")

        enc2_events = [
            _make_event("e3", "PAT1", "ADMIT", ts + timedelta(hours=8),
                        source_record_id="src3"),
            _make_event("e4", "PAT1", "DISCHARGE", ts + timedelta(hours=20)),
        ]
        enc2 = _make_encounter("PAT1", "FAC_001", enc2_events, encounter_id="ENC_002")

        stage = DedupStage()
        stage.encounters_in = [enc1, enc2]
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=_make_context())

        # 2 encounters merged into 1
        assert stage.encounters_merged == 1

    def test_metrics_stage_name(self) -> None:
        from asre.dedup.stage import DedupStage

        stage = DedupStage()
        stage.encounters_in = []
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=_make_context())
        assert stage.metrics.stage_name == "dedup"

    def test_metrics_status_success(self) -> None:
        from asre.dedup.stage import DedupStage

        stage = DedupStage()
        stage.encounters_in = []
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=_make_context())
        assert stage.metrics.status == "success"


# --- Config-Driven Tests ---


class TestDedupStageConfig:
    """Verify DedupStage reads config from PipelineContext."""

    def test_uses_config_source_priority(self) -> None:
        """Source priority from config should determine which duplicate is kept."""
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_system="adt_vendor_x",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e2", "PAT1", "ADMIT", ts + timedelta(minutes=15),
                        source_system="claims_clearinghouse",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events)

        # With claims higher priority than ADT
        stage = DedupStage()
        stage.encounters_in = [enc]
        context = _make_context(source_priority={"adt": 40, "claims": 100, "auth": 10})
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=context)

        enc_out = stage.encounters[0]
        admit_events = [e for e in enc_out.events if e.event_type == "ADMIT"]
        kept = [e for e in admit_events if e.role_in_encounter != "duplicate"]
        assert len(kept) == 1
        assert kept[0].source_system.startswith("claims")

    def test_uses_default_config_when_missing(self) -> None:
        """DedupStage should work with empty config."""
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        events = [
            _make_event("e1", "PAT1", "ADMIT", ts),
            _make_event("e2", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc = _make_encounter("PAT1", "FAC_001", events)

        stage = DedupStage()
        stage.encounters_in = [enc]
        context = PipelineContext(run_id="run_1", config={}, mode="full")
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=context)

        assert len(stage.encounters) == 1


# --- End-to-End Test ---


class TestDedupStageEndToEnd:
    """Full batch processing end-to-end with known duplicates."""

    def test_mixed_encounters_with_duplicates_and_overlaps(self) -> None:
        """Complex scenario: event-level dupes + encounter-level overlap."""
        from asre.dedup.stage import DedupStage

        ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        # Encounter 1: PAT1 at FAC_001 with a duplicate ADMIT
        enc1_events = [
            _make_event("e1", "PAT1", "ADMIT", ts, source_system="adt_vendor_x",
                        source_record_id="src1",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e2", "PAT1", "ADMIT", ts + timedelta(minutes=10),
                        source_system="claims_clearinghouse",
                        source_record_id="src2",
                        ingested_at=datetime(2024, 1, 14, tzinfo=timezone.utc)),
            _make_event("e3", "PAT1", "DISCHARGE", ts + timedelta(hours=24)),
        ]
        enc1 = _make_encounter("PAT1", "FAC_001", enc1_events, encounter_id="ENC_001")

        # Encounter 2: PAT2 at FAC_002 with no duplicates
        enc2_events = [
            _make_event("e4", "PAT2", "ADMIT", ts, source_record_id="src4"),
            _make_event("e5", "PAT2", "DISCHARGE", ts + timedelta(hours=12)),
        ]
        enc2 = _make_encounter("PAT2", "FAC_002", enc2_events, encounter_id="ENC_002")

        stage = DedupStage()
        stage.encounters_in = [enc1, enc2]
        context = _make_context(source_priority={"adt": 100, "claims": 80, "auth": 40})
        stage.run(batch=EventBatch(batch_id="b1", events=[]), context=context)

        # Both encounters remain (different patients)
        assert len(stage.encounters) == 2

        # Event-level dedup: 1 duplicate found
        assert stage.duplicates_found == 1

        # Total events before: 3 + 2 = 5
        assert stage.events_before == 5

        # Metrics recorded
        assert stage.metrics.status == "success"
