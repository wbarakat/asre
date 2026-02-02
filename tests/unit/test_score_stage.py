"""Tests for ScoreStage (US-068).

Tests the scoring pipeline stage that processes encounters and returns
scored encounters with confidence scores, flags, and stale detection.

Records stage metrics: encounters_scored, avg_score,
score_distribution (high/medium/low/very_low counts).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext
from asre.reconcile.stage import ReconciledEncounter
from asre.score.stage import ScoreStage
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    *,
    event_type: str = "ADMIT",
    source_system: str = "adt_vendor_x",
    patient_key: str = "PAT_001",
    facility_canonical_id: str | None = "FAC_001",
    patient_class: str | None = None,
    event_ts: datetime | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt_001",
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts or datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id="src_001",
        facility_raw="Test Hospital",
        facility_canonical_id=facility_canonical_id,
        admit_flag=(event_type in ("ADMIT", "CLAIM_ADMIT")),
        discharge_flag=(event_type in ("DISCHARGE", "CLAIM_DISCHARGE")),
        auth_flag=False,
        patient_class=patient_class,
        drg=None,
        principal_diagnosis=None,
        diagnosis_codes=None,
        auth_status=None,
        payer_id=None,
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        batch_id="batch_001",
        _raw_payload={},
    )


def _make_encounter(
    events: list[CanonicalEvent],
    *,
    patient_key: str = "PAT_001",
    facility_canonical_id: str | None = "FAC_001",
    has_discharge: bool = False,
    status: str = "open",
) -> StitchedEncounter:
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
        events=events,
        last_event_ts=events[-1].event_ts if events else None,
        encounter_type="inpatient",
    )
    enc.has_discharge = has_discharge
    enc.status = status
    return enc


def _make_reconciled(
    encounter: StitchedEncounter,
    flags: list[str] | None = None,
) -> ReconciledEncounter:
    rec = ReconciledEncounter(encounter)
    rec.confidence_flags = flags or []
    return rec


def _make_context(config: dict[str, Any] | None = None) -> PipelineContext:
    return PipelineContext(
        run_id="run_test_001",
        config=config or {},
        mode="full",
    )


class TestScoreStage:
    """Tests for ScoreStage pipeline stage."""

    def test_scores_encounters_and_sets_confidence_score(self) -> None:
        """ScoreStage sets confidence_score on each encounter."""
        events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x"),
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch"),
        ]
        enc = _make_encounter(events, has_discharge=False)
        reconciled = _make_reconciled(enc)

        stage = ScoreStage()
        stage.encounters_in = [reconciled]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert len(stage.encounters) == 1
        scored = stage.encounters[0]
        assert scored.confidence_score is not None
        assert 0.0 <= scored.confidence_score <= 1.0

    def test_populates_confidence_flags(self) -> None:
        """ScoreStage populates confidence_flags with signals and penalties."""
        events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x"),
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch"),
        ]
        enc = _make_encounter(events, has_discharge=False)
        reconciled = _make_reconciled(enc, flags=["MISSING_DISCHARGE"])

        stage = ScoreStage()
        stage.encounters_in = [reconciled]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        scored = stage.encounters[0]
        # Should have both positive signals and penalty flags
        assert "HAS_CLAIMS" in scored.confidence_flags
        assert "HAS_ADT_ADMIT" in scored.confidence_flags
        assert "MISSING_DISCHARGE" in scored.confidence_flags

    def test_tracks_encounters_scored(self) -> None:
        """Stage records encounters_scored count."""
        events = [_make_event()]
        enc1 = _make_encounter(events)
        enc2 = _make_encounter(events, patient_key="PAT_002")

        stage = ScoreStage()
        stage.encounters_in = [
            _make_reconciled(enc1),
            _make_reconciled(enc2),
        ]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.encounters_scored == 2

    def test_computes_avg_score(self) -> None:
        """Stage computes average confidence score."""
        # High-quality encounter with many signals
        high_events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x"),
            _make_event(event_type="DISCHARGE", source_system="adt_vendor_x"),
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch"),
            _make_event(event_type="CLAIM_DISCHARGE", source_system="claims_ch"),
        ]
        high_enc = _make_encounter(high_events, has_discharge=True)
        high_rec = _make_reconciled(high_enc)

        # Low-quality encounter with few signals
        low_events = [_make_event(event_type="ADMIT", source_system="adt_vendor_x")]
        low_enc = _make_encounter(low_events)
        low_rec = _make_reconciled(low_enc)

        stage = ScoreStage()
        stage.encounters_in = [high_rec, low_rec]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.avg_score is not None
        assert 0.0 <= stage.avg_score <= 1.0

    def test_score_distribution(self) -> None:
        """Stage computes score distribution: high/medium/low/very_low counts."""
        # Create encounters that will produce different score levels
        # High: all signals -> score ~ 1.0 (0.85-1.0)
        all_events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x", patient_class="inpatient"),
            _make_event(event_type="DISCHARGE", source_system="adt_vendor_x", patient_class="inpatient"),
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch", patient_class="inpatient"),
            _make_event(event_type="CLAIM_DISCHARGE", source_system="claims_ch", patient_class="inpatient"),
            _make_event(event_type="AUTH_APPROVED", source_system="auth_portal", patient_class="inpatient"),
        ]
        high_enc = _make_encounter(all_events, has_discharge=True)
        high_rec = _make_reconciled(high_enc)

        # Very low: minimal signals + penalty -> score < 0.30
        low_events = [
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch"),
        ]
        vlow_enc = _make_encounter(low_events)
        vlow_rec = _make_reconciled(vlow_enc, flags=["CLAIMS_ONLY_ENCOUNTER"])

        stage = ScoreStage()
        stage.encounters_in = [high_rec, vlow_rec]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        dist = stage.score_distribution
        assert "high" in dist
        assert "medium" in dist
        assert "low" in dist
        assert "very_low" in dist
        assert sum(dist.values()) == 2

    def test_records_stage_metrics(self) -> None:
        """Stage records metrics via StageMetrics context manager."""
        events = [_make_event()]
        enc = _make_encounter(events)

        stage = ScoreStage()
        stage.encounters_in = [_make_reconciled(enc)]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.metrics.records_in == 1
        assert stage.metrics.records_out == 1
        assert stage.metrics.status == "success"

    def test_stale_detection_with_facility_registry(self) -> None:
        """Stage looks up facility_type from registry for stale detection."""
        # Create an open encounter that's old enough to be stale for acute (30d)
        old_ts = datetime.now(tz=timezone.utc) - timedelta(days=35)
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                event_ts=old_ts,
            ),
        ]
        enc = _make_encounter(events, has_discharge=False)
        reconciled = _make_reconciled(enc)

        # Provide facility_registry in config with facility_type=acute
        config: dict[str, Any] = {
            "facility_registry_map": {"FAC_001": "acute"},
        }
        stage = ScoreStage()
        stage.encounters_in = [reconciled]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context(config))

        scored = stage.encounters[0]
        assert "STALE_OPEN_ENCOUNTER" in scored.confidence_flags

    def test_stale_detection_snf_not_stale(self) -> None:
        """SNF with 100 days open is not stale (threshold 120 days)."""
        old_ts = datetime.now(tz=timezone.utc) - timedelta(days=100)
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                event_ts=old_ts,
            ),
        ]
        enc = _make_encounter(events, has_discharge=False)
        reconciled = _make_reconciled(enc)

        config: dict[str, Any] = {
            "facility_registry_map": {"FAC_001": "snf"},
        }
        stage = ScoreStage()
        stage.encounters_in = [reconciled]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context(config))

        scored = stage.encounters[0]
        assert "STALE_OPEN_ENCOUNTER" not in scored.confidence_flags

    def test_uses_config_signal_weights(self) -> None:
        """Stage uses signal weights from config when provided."""
        events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x"),
            _make_event(event_type="DISCHARGE", source_system="adt_vendor_x"),
        ]
        enc = _make_encounter(events, has_discharge=True)
        reconciled = _make_reconciled(enc)

        # Custom weights: only HAS_ADT_ADMIT matters (weight 100)
        config: dict[str, Any] = {
            "confidence_scoring": {
                "signal_weights": {
                    "HAS_CLAIMS": 0,
                    "HAS_ADT_ADMIT": 100,
                    "HAS_ADT_DISCHARGE": 0,
                    "HAS_AUTH": 0,
                    "FACILITY_RESOLVED": 0,
                    "TIMESTAMPS_CONSISTENT": 0,
                    "PATIENT_CLASS_CONSISTENT": 0,
                },
            },
        }
        stage = ScoreStage()
        stage.encounters_in = [reconciled]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context(config))

        scored = stage.encounters[0]
        assert scored.confidence_score == pytest.approx(1.0)

    def test_empty_encounters_list(self) -> None:
        """Stage handles empty encounter list gracefully."""
        stage = ScoreStage()
        stage.encounters_in = []
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.encounters == []
        assert stage.encounters_scored == 0
        assert stage.avg_score == 0.0

    def test_batch_scoring_mixed_quality(self) -> None:
        """Full batch with mixed-quality encounters produces correct results."""
        # High quality (ADT + claims + auth + resolved facility)
        high_events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x", patient_class="inpatient"),
            _make_event(event_type="DISCHARGE", source_system="adt_vendor_x", patient_class="inpatient"),
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch", patient_class="inpatient"),
            _make_event(event_type="CLAIM_DISCHARGE", source_system="claims_ch", patient_class="inpatient"),
            _make_event(event_type="AUTH_APPROVED", source_system="auth_portal", patient_class="inpatient"),
        ]
        high = _make_reconciled(_make_encounter(high_events, has_discharge=True))

        # Medium quality (ADT only)
        med_events = [
            _make_event(event_type="ADMIT", source_system="adt_vendor_x"),
            _make_event(event_type="DISCHARGE", source_system="adt_vendor_x"),
        ]
        med = _make_reconciled(_make_encounter(med_events, has_discharge=True))

        # Low quality (claims only + penalty)
        low_events = [
            _make_event(event_type="CLAIM_ADMIT", source_system="claims_ch"),
        ]
        low = _make_reconciled(
            _make_encounter(low_events),
            flags=["CLAIMS_ONLY_ENCOUNTER", "MISSING_DISCHARGE"],
        )

        stage = ScoreStage()
        stage.encounters_in = [high, med, low]
        batch = EventBatch(batch_id="b1", events=[])
        stage.run(batch, _make_context())

        assert stage.encounters_scored == 3
        assert len(stage.encounters) == 3

        scores = [e.confidence_score for e in stage.encounters]
        # High quality should score highest
        assert scores[0] > scores[1]
        # Medium should score higher than low
        assert scores[1] > scores[2]
