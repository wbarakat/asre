"""Tests for ConfidenceScorer (US-064).

Tests the weighted sum of binary signals normalized to [0, 1].

7 signals with default weights:
  HAS_CLAIMS (30), HAS_ADT_ADMIT (20), HAS_ADT_DISCHARGE (10),
  HAS_AUTH (10), FACILITY_RESOLVED (5), TIMESTAMPS_CONSISTENT (15),
  PATIENT_CLASS_CONSISTENT (10)

Maximum raw score = 100, normalized to 1.0.
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.canonical_event import CanonicalEvent
from asre.reconcile.stage import ReconciledEncounter
from asre.score.confidence_scorer import ConfidenceScorer
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    *,
    event_type: str = "ADMIT",
    source_system: str = "adt_vendor_x",
    patient_key: str = "PAT_001",
    facility_canonical_id: str | None = "FAC_001",
    admit_flag: bool = False,
    discharge_flag: bool = False,
    patient_class: str | None = None,
) -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt_001",
        patient_key=patient_key,
        event_type=event_type,
        event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id="src_001",
        facility_raw="Test Hospital",
        facility_canonical_id=facility_canonical_id,
        admit_flag=admit_flag,
        discharge_flag=discharge_flag,
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


class TestConfidenceScorer:
    """Tests for base confidence score computation."""

    def test_all_signals_present_produces_score_1(self) -> None:
        """All 7 signals present -> score = 100/100 = 1.0."""
        # Encounter with claims, ADT admit, ADT discharge, auth, resolved facility,
        # consistent timestamps, consistent patient class
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="DISCHARGE",
                source_system="adt_vendor_x",
                discharge_flag=True,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="AUTH_APPROVED",
                source_system="auth_portal",
            ),
        ]
        enc = _make_encounter(events, has_discharge=True, status="closed")
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        assert score == 1.0

    def test_only_has_claims_produces_030(self) -> None:
        """Only HAS_CLAIMS signal -> score = 30/100 = 0.30."""
        events = [
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                facility_canonical_id=None,  # unresolved -> no FACILITY_RESOLVED
                patient_class=None,  # no patient_class -> empty set -> consistent (<=1)
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        # TIMESTAMP_MISMATCH -> no TIMESTAMPS_CONSISTENT
        # patient_class=None means patient_classes set is empty (<=1) -> consistent
        # So we need to also break PATIENT_CLASS_CONSISTENT. Use two different classes.
        events2 = [
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_DISCHARGE",
                source_system="claims_clearinghouse",
                discharge_flag=True,
                facility_canonical_id=None,
                patient_class="observation",  # different -> inconsistent
            ),
        ]
        enc2 = _make_encounter(events2, facility_canonical_id=None)
        rec = _make_reconciled(enc2, flags=["TIMESTAMP_MISMATCH"])

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        assert score == 30 / 100

    def test_has_claims_and_adt_admit_produces_050(self) -> None:
        """HAS_CLAIMS + HAS_ADT_ADMIT -> score = 50/100 = 0.50."""
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                facility_canonical_id=None,  # unresolved
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="observation",  # inconsistent -> no PATIENT_CLASS_CONSISTENT
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        # TIMESTAMP_MISMATCH flag means timestamps not consistent
        rec = _make_reconciled(enc, flags=["TIMESTAMP_MISMATCH"])

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        assert score == 50 / 100

    def test_custom_weights(self) -> None:
        """Custom signal weights are respected."""
        # Only HAS_CLAIMS active: no ADT, no auth, unresolved facility,
        # TIMESTAMP_MISMATCH flag, inconsistent patient_class
        events = [
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_DISCHARGE",
                source_system="claims_clearinghouse",
                discharge_flag=True,
                facility_canonical_id=None,
                patient_class="observation",
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        rec = _make_reconciled(enc, flags=["TIMESTAMP_MISMATCH"])

        custom_weights = {
            "HAS_CLAIMS": 50,
            "HAS_ADT_ADMIT": 10,
            "HAS_ADT_DISCHARGE": 10,
            "HAS_AUTH": 10,
            "FACILITY_RESOLVED": 5,
            "TIMESTAMPS_CONSISTENT": 10,
            "PATIENT_CLASS_CONSISTENT": 5,
        }
        scorer = ConfidenceScorer(signal_weights=custom_weights)
        score = scorer.compute_score(rec)

        assert score == 50 / 100

    def test_max_raw_score_is_sum_of_weights(self) -> None:
        """Maximum raw score equals sum of all weights, normalized to 1.0."""
        scorer = ConfidenceScorer()
        assert scorer.max_score == 100

    def test_evaluate_signals_returns_active_signals(self) -> None:
        """evaluate_signals returns dict of signal name -> bool."""
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                patient_class="inpatient",
            ),
        ]
        enc = _make_encounter(events)
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        signals = scorer.evaluate_signals(rec)

        assert signals["HAS_CLAIMS"] is True
        assert signals["HAS_ADT_ADMIT"] is True
        assert signals["HAS_ADT_DISCHARGE"] is False
        assert signals["HAS_AUTH"] is False
        assert signals["FACILITY_RESOLVED"] is True

    def test_no_signals_produces_score_0(self) -> None:
        """No active signals -> score = 0.0."""
        # Unknown source, unresolved facility, TIMESTAMP_MISMATCH, inconsistent patient_class
        events = [
            _make_event(
                event_type="UNKNOWN",
                source_system="unknown_source",
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="UNKNOWN",
                source_system="unknown_source",
                facility_canonical_id=None,
                patient_class="observation",
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        rec = _make_reconciled(enc, flags=["TIMESTAMP_MISMATCH"])

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        assert score == 0.0
