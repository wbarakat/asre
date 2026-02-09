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

import pytest

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
    facility_match_type: str | None = None,
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
        facility_match_type=facility_match_type,
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

    def test_facility_new_is_not_resolved(self) -> None:
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                patient_class="inpatient",
                facility_canonical_id="FAC_001",
                facility_match_type="new",
            ),
        ]
        enc = _make_encounter(events)
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        signals = scorer.evaluate_signals(rec)

        assert signals["FACILITY_RESOLVED"] is False

    def test_only_has_claims_base_score_030(self) -> None:
        """Only HAS_CLAIMS signal -> base score = 30/100 = 0.30.

        TIMESTAMP_MISMATCH disables TIMESTAMPS_CONSISTENT and also applies
        -0.10 penalty (US-065), so final score = 0.30 - 0.10 = 0.20.
        """
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

        # Base 0.30 - TIMESTAMP_MISMATCH penalty 0.10 = 0.20
        assert score == pytest.approx(0.20)

    def test_has_claims_and_adt_admit_base_score_050(self) -> None:
        """HAS_CLAIMS + HAS_ADT_ADMIT -> base score = 50/100 = 0.50.

        TIMESTAMP_MISMATCH also applies -0.10 penalty (US-065),
        so final score = 0.50 - 0.10 = 0.40.
        """
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
        rec = _make_reconciled(enc, flags=["TIMESTAMP_MISMATCH"])

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        # Base 0.50 - TIMESTAMP_MISMATCH penalty 0.10 = 0.40
        assert score == 0.40

    def test_custom_signal_weights(self) -> None:
        """Custom signal weights are respected."""
        # Only HAS_CLAIMS active: no ADT, no auth, unresolved facility,
        # inconsistent patient_class. No penalty flags.
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
        # No TIMESTAMP_MISMATCH so TIMESTAMPS_CONSISTENT=True
        # But we want only HAS_CLAIMS active. Use flags=[] and adjust weights.
        rec = _make_reconciled(enc, flags=[])

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

        # HAS_CLAIMS(50) + TIMESTAMPS_CONSISTENT(10) = 60/100 = 0.60
        assert score == 60 / 100

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


class TestPenaltyApplication:
    """Tests for US-065: Penalty application to confidence score."""

    def test_missing_discharge_penalty(self) -> None:
        """MISSING_DISCHARGE penalty (-0.15) reduces score from base.

        PRD: base score 0.50 with MISSING_DISCHARGE produces 0.35.
        We construct a base of 0.50 using custom signal weights.
        """
        # HAS_CLAIMS + HAS_ADT_ADMIT active, nothing else
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="observation",  # inconsistent
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        # MISSING_DISCHARGE is the only penalty flag.
        # No TIMESTAMP_MISMATCH -> TIMESTAMPS_CONSISTENT=True
        # But we want base=0.50. Active signals with defaults:
        # HAS_CLAIMS(30)+HAS_ADT_ADMIT(20)+TIMESTAMPS_CONSISTENT(15)=65/100=0.65
        # Use custom weights: HAS_CLAIMS=25, HAS_ADT_ADMIT=25, rest=0 active besides these two
        custom_signals = {
            "HAS_CLAIMS": 25,
            "HAS_ADT_ADMIT": 25,
            "HAS_ADT_DISCHARGE": 25,
            "HAS_AUTH": 25,
            "FACILITY_RESOLVED": 0,
            "TIMESTAMPS_CONSISTENT": 0,
            "PATIENT_CLASS_CONSISTENT": 0,
        }
        rec = _make_reconciled(enc, flags=["MISSING_DISCHARGE"])
        scorer = ConfidenceScorer(signal_weights=custom_signals)
        score = scorer.compute_score(rec)

        # Base: (25+25) / 100 = 0.50
        # Penalty: MISSING_DISCHARGE = -0.15
        # Final: 0.50 - 0.15 = 0.35
        assert score == 0.35

    def test_penalties_floor_at_zero(self) -> None:
        """Base score 0.20 with penalties totaling 0.30 produces 0.0 (floored)."""
        # Only HAS_ADT_ADMIT (20) = 20/100 = 0.20 base
        # ORPHAN_DISCHARGE (-0.20) + FACILITY_UNRESOLVED (-0.10) = -0.30
        # 0.20 - 0.30 = -0.10 -> floored to 0.0
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="observation",
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        rec = _make_reconciled(
            enc,
            flags=["TIMESTAMP_MISMATCH", "ORPHAN_DISCHARGE", "FACILITY_UNRESOLVED"],
        )

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        assert score == 0.0

    def test_all_penalties_applied(self) -> None:
        """All 9 penalty types reduce the score."""
        # All signals present -> base 1.0
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

        all_penalties = [
            "MISSING_DISCHARGE",        # -0.15
            "ORPHAN_DISCHARGE",         # -0.20
            "TIMESTAMP_MISMATCH",       # -0.10
            "CLAIMS_ONLY_ENCOUNTER",    # -0.10
            "STALE_OPEN_ENCOUNTER",     # -0.20
            "DUPLICATE_DETECTED",       # -0.05
            "FACILITY_UNRESOLVED",      # -0.10
            "AUTH_WITHOUT_ADMIT",       # -0.05
            "CANCELLED_AND_REOPENED",   # -0.05
        ]
        rec = _make_reconciled(enc, flags=all_penalties)

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        # Base: 1.0 (all signals except TIMESTAMPS_CONSISTENT due to TIMESTAMP_MISMATCH)
        # Actually TIMESTAMP_MISMATCH in flags means TIMESTAMPS_CONSISTENT = False
        # Base: (30+20+10+10+5+0+10)/100 = 85/100 = 0.85
        # Penalties: 0.15+0.20+0.10+0.10+0.20+0.05+0.10+0.05+0.05 = 1.0
        # 0.85 - 1.0 = -0.15 -> floored to 0.0
        assert score == 0.0

    def test_no_penalties_score_unchanged(self) -> None:
        """No penalty flags means base score is unchanged."""
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
        # No flags at all -> TIMESTAMPS_CONSISTENT=True, no penalties
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        score = scorer.compute_score(rec)

        # HAS_CLAIMS(30) + TIMESTAMPS_CONSISTENT(15) = 45/100 = 0.45
        # No penalty flags, score unchanged
        assert score == 0.45

    def test_custom_penalty_weights(self) -> None:
        """Custom penalty weights are respected."""
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="observation",
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        rec = _make_reconciled(enc, flags=["TIMESTAMP_MISMATCH", "MISSING_DISCHARGE"])

        # Base: HAS_CLAIMS(30) + HAS_ADT_ADMIT(20) = 0.50
        # Custom penalty for MISSING_DISCHARGE = -0.25
        custom_penalties = {"MISSING_DISCHARGE": -0.25}
        scorer = ConfidenceScorer(penalty_weights=custom_penalties)
        score = scorer.compute_score(rec)

        assert score == 0.25


class TestConfidenceFlagsPopulation:
    """Tests for US-066: Populate confidence_flags array.

    confidence_flags should contain names of all active signals (signal=1)
    AND all applied penalties.
    """

    def test_claims_and_missing_discharge_flags(self) -> None:
        """Encounter with claims + missing discharge produces flags
        including both HAS_CLAIMS and MISSING_DISCHARGE."""
        events = [
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                patient_class="inpatient",
            ),
        ]
        enc = _make_encounter(events)
        # Pre-existing penalty flags from reconcile stage
        rec = _make_reconciled(enc, flags=["MISSING_DISCHARGE"])

        scorer = ConfidenceScorer()
        flags = scorer.build_confidence_flags(rec)

        # Active signals should be present
        assert "HAS_CLAIMS" in flags
        assert "TIMESTAMPS_CONSISTENT" in flags  # no TIMESTAMP_MISMATCH
        assert "FACILITY_RESOLVED" in flags

        # Penalty flags should also be present
        assert "MISSING_DISCHARGE" in flags

        # Inactive signals should NOT be present
        assert "HAS_ADT_ADMIT" not in flags
        assert "HAS_ADT_DISCHARGE" not in flags
        assert "HAS_AUTH" not in flags

    def test_all_signals_and_no_penalties(self) -> None:
        """All signals active and no penalties produces only signal flags."""
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
        flags = scorer.build_confidence_flags(rec)

        # All 7 signals active
        assert "HAS_CLAIMS" in flags
        assert "HAS_ADT_ADMIT" in flags
        assert "HAS_ADT_DISCHARGE" in flags
        assert "HAS_AUTH" in flags
        assert "FACILITY_RESOLVED" in flags
        assert "TIMESTAMPS_CONSISTENT" in flags
        assert "PATIENT_CLASS_CONSISTENT" in flags
        assert len(flags) == 7  # no penalties

    def test_penalty_flags_included_when_applied(self) -> None:
        """Penalty flags from reconcile stage are included in output."""
        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
                facility_canonical_id=None,
                patient_class="inpatient",
            ),
        ]
        enc = _make_encounter(events, facility_canonical_id=None)
        rec = _make_reconciled(
            enc,
            flags=["MISSING_DISCHARGE", "FACILITY_UNRESOLVED", "TIMESTAMP_MISMATCH"],
        )

        scorer = ConfidenceScorer()
        flags = scorer.build_confidence_flags(rec)

        # Penalty flags present
        assert "MISSING_DISCHARGE" in flags
        assert "FACILITY_UNRESOLVED" in flags
        assert "TIMESTAMP_MISMATCH" in flags

        # Active signals present
        assert "HAS_ADT_ADMIT" in flags

        # TIMESTAMPS_CONSISTENT should NOT be present (TIMESTAMP_MISMATCH disables it)
        assert "TIMESTAMPS_CONSISTENT" not in flags
        # FACILITY_RESOLVED should NOT be present (facility_canonical_id is None)
        assert "FACILITY_RESOLVED" not in flags

    def test_no_duplicate_flags(self) -> None:
        """Flags list contains no duplicates even if penalty name matches signal."""
        events = [
            _make_event(
                event_type="CLAIM_ADMIT",
                source_system="claims_clearinghouse",
                admit_flag=True,
                patient_class="inpatient",
            ),
        ]
        enc = _make_encounter(events)
        rec = _make_reconciled(enc, flags=["CLAIMS_ONLY_ENCOUNTER"])

        scorer = ConfidenceScorer()
        flags = scorer.build_confidence_flags(rec)

        # No duplicates
        assert len(flags) == len(set(flags))


class TestStaleEncounterDetection:
    """Tests for US-067: Stale encounter detection with facility-type-aware thresholds.

    STALE_OPEN_ENCOUNTER flag applied when encounter is open (no discharge) AND
    open duration exceeds facility-type threshold.

    Default thresholds: acute (30 days), ed_standalone (3 days), ltach (90 days),
    snf (120 days), rehab (60 days), psych (90 days), default (30 days).
    """

    def test_acute_facility_open_31_days_produces_stale_flag(self) -> None:
        """Acute facility, open 31 days produces STALE_OPEN_ENCOUNTER."""
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        now = datetime(2024, 2, 1, 10, 0, tzinfo=timezone.utc)  # 31 days later

        events = [
            _make_event(
                event_type="ADMIT",
                source_system="adt_vendor_x",
                admit_flag=True,
            ),
        ]
        events[0] = CanonicalEvent(
            event_id="evt_001",
            patient_key="PAT_001",
            event_type="ADMIT",
            event_ts=admit_ts,
            source_system="adt_vendor_x",
            source_record_id="src_001",
            facility_raw="Test Hospital",
            facility_canonical_id="FAC_001",
            admit_flag=True,
            discharge_flag=False,
            auth_flag=False,
            patient_class="inpatient",
            drg=None,
            principal_diagnosis=None,
            diagnosis_codes=None,
            auth_status=None,
            payer_id=None,
            ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            batch_id="batch_001",
            _raw_payload={},
        )

        enc = _make_encounter(events, has_discharge=False, status="open")
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        stale_flags = scorer.detect_stale_encounter(rec, now=now, facility_type="acute")

        assert "STALE_OPEN_ENCOUNTER" in stale_flags

    def test_snf_open_100_days_no_stale_flag(self) -> None:
        """SNF, open 100 days produces no stale flag (threshold 120)."""
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        now = datetime(2024, 4, 10, 10, 0, tzinfo=timezone.utc)  # ~100 days later

        events = [
            CanonicalEvent(
                event_id="evt_001",
                patient_key="PAT_001",
                event_type="ADMIT",
                event_ts=admit_ts,
                source_system="adt_vendor_x",
                source_record_id="src_001",
                facility_raw="SNF Facility",
                facility_canonical_id="FAC_002",
                admit_flag=True,
                discharge_flag=False,
                auth_flag=False,
                patient_class="inpatient",
                drg=None,
                principal_diagnosis=None,
                diagnosis_codes=None,
                auth_status=None,
                payer_id=None,
                ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                batch_id="batch_001",
                _raw_payload={},
            ),
        ]

        enc = _make_encounter(events, has_discharge=False, status="open")
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        stale_flags = scorer.detect_stale_encounter(rec, now=now, facility_type="snf")

        assert "STALE_OPEN_ENCOUNTER" not in stale_flags
        assert stale_flags == []

    def test_unknown_facility_type_open_31_days_produces_stale_flag(self) -> None:
        """Unknown facility type, open 31 days produces STALE_OPEN_ENCOUNTER (default 30)."""
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        now = datetime(2024, 2, 1, 10, 0, tzinfo=timezone.utc)  # 31 days later

        events = [
            CanonicalEvent(
                event_id="evt_001",
                patient_key="PAT_001",
                event_type="ADMIT",
                event_ts=admit_ts,
                source_system="adt_vendor_x",
                source_record_id="src_001",
                facility_raw="Unknown Facility",
                facility_canonical_id="FAC_003",
                admit_flag=True,
                discharge_flag=False,
                auth_flag=False,
                patient_class="inpatient",
                drg=None,
                principal_diagnosis=None,
                diagnosis_codes=None,
                auth_status=None,
                payer_id=None,
                ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                batch_id="batch_001",
                _raw_payload={},
            ),
        ]

        enc = _make_encounter(events, has_discharge=False, status="open")
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        stale_flags = scorer.detect_stale_encounter(rec, now=now, facility_type=None)

        assert "STALE_OPEN_ENCOUNTER" in stale_flags

    def test_closed_encounter_never_stale(self) -> None:
        """An encounter with a discharge is never flagged as stale."""
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        now = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)  # 150 days later

        events = [
            CanonicalEvent(
                event_id="evt_001",
                patient_key="PAT_001",
                event_type="ADMIT",
                event_ts=admit_ts,
                source_system="adt_vendor_x",
                source_record_id="src_001",
                facility_raw="Test Hospital",
                facility_canonical_id="FAC_001",
                admit_flag=True,
                discharge_flag=False,
                auth_flag=False,
                patient_class="inpatient",
                drg=None,
                principal_diagnosis=None,
                diagnosis_codes=None,
                auth_status=None,
                payer_id=None,
                ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                batch_id="batch_001",
                _raw_payload={},
            ),
        ]

        enc = _make_encounter(events, has_discharge=True, status="closed")
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        stale_flags = scorer.detect_stale_encounter(rec, now=now, facility_type="acute")

        assert stale_flags == []

    def test_acute_facility_open_29_days_no_stale_flag(self) -> None:
        """Acute facility open 29 days is within threshold (30), no stale flag."""
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        now = datetime(2024, 1, 30, 10, 0, tzinfo=timezone.utc)  # 29 days later

        events = [
            CanonicalEvent(
                event_id="evt_001",
                patient_key="PAT_001",
                event_type="ADMIT",
                event_ts=admit_ts,
                source_system="adt_vendor_x",
                source_record_id="src_001",
                facility_raw="Test Hospital",
                facility_canonical_id="FAC_001",
                admit_flag=True,
                discharge_flag=False,
                auth_flag=False,
                patient_class="inpatient",
                drg=None,
                principal_diagnosis=None,
                diagnosis_codes=None,
                auth_status=None,
                payer_id=None,
                ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                batch_id="batch_001",
                _raw_payload={},
            ),
        ]

        enc = _make_encounter(events, has_discharge=False, status="open")
        rec = _make_reconciled(enc, flags=[])

        scorer = ConfidenceScorer()
        stale_flags = scorer.detect_stale_encounter(rec, now=now, facility_type="acute")

        assert stale_flags == []

    def test_custom_stale_thresholds(self) -> None:
        """Custom stale thresholds override defaults."""
        admit_ts = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        now = datetime(2024, 1, 11, 10, 0, tzinfo=timezone.utc)  # 10 days later

        events = [
            CanonicalEvent(
                event_id="evt_001",
                patient_key="PAT_001",
                event_type="ADMIT",
                event_ts=admit_ts,
                source_system="adt_vendor_x",
                source_record_id="src_001",
                facility_raw="Test Hospital",
                facility_canonical_id="FAC_001",
                admit_flag=True,
                discharge_flag=False,
                auth_flag=False,
                patient_class="inpatient",
                drg=None,
                principal_diagnosis=None,
                diagnosis_codes=None,
                auth_status=None,
                payer_id=None,
                ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
                batch_id="batch_001",
                _raw_payload={},
            ),
        ]

        enc = _make_encounter(events, has_discharge=False, status="open")
        rec = _make_reconciled(enc, flags=[])

        custom_thresholds = {"acute": 5, "default": 5}
        scorer = ConfidenceScorer(stale_thresholds=custom_thresholds)
        stale_flags = scorer.detect_stale_encounter(rec, now=now, facility_type="acute")

        assert "STALE_OPEN_ENCOUNTER" in stale_flags
