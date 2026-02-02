"""Tests for ReconcileStage — pipeline stage for reconciliation (US-063)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext
from asre.reconcile.stage import ReconcileStage
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    event_id: str,
    event_type: str,
    event_ts: datetime,
    source_system: str,
    patient_key: str = "PAT-001",
    source_record_id: str = "SRC-001",
    facility_raw: str = "Test Hospital",
    facility_canonical_id: str | None = "FAC-001",
    patient_class: str | None = None,
    admit_flag: bool | None = None,
    discharge_flag: bool | None = None,
    drg: str | None = None,
    principal_diagnosis: str | None = None,
    diagnosis_codes: list[dict[str, Any]] | None = None,
    payer_id: str | None = None,
) -> CanonicalEvent:
    """Helper to create canonical events for testing."""
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts,
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw=facility_raw,
        facility_canonical_id=facility_canonical_id,
        ingested_at=datetime(2024, 1, 20, 0, 0, tzinfo=timezone.utc),
        batch_id="batch-001",
        patient_class=patient_class,
        admit_flag=admit_flag,
        discharge_flag=discharge_flag,
        drg=drg,
        principal_diagnosis=principal_diagnosis,
        diagnosis_codes=diagnosis_codes,
        payer_id=payer_id,
    )


def _make_encounter(
    events: list[CanonicalEvent],
    patient_key: str = "PAT-001",
    facility_canonical_id: str | None = "FAC-001",
    has_discharge: bool = False,
    status: str = "open",
    encounter_id: str | None = None,
) -> StitchedEncounter:
    """Helper to create a StitchedEncounter."""
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
        events=events,
        has_discharge=has_discharge,
        status=status,
        encounter_id=encounter_id,
    )
    if events:
        enc.last_event_ts = max(e.event_ts for e in events)
    return enc


def _make_context(config: dict[str, Any] | None = None) -> PipelineContext:
    """Create a PipelineContext for testing."""
    return PipelineContext(
        run_id="run_test_001",
        config=config or {},
        mode="full",
    )


class TestReconcileStageBasic:
    """Test basic ReconcileStage operation."""

    def test_reconcile_stage_processes_encounters(self) -> None:
        """ReconcileStage processes encounters and stores reconciled results."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        events = [
            _make_event("E1", "ADMIT", base_ts, "adt_vendor_x", patient_class="inpatient"),
            _make_event(
                "E2", "DISCHARGE", base_ts + timedelta(hours=48),
                "adt_vendor_x", patient_class="inpatient",
            ),
        ]

        enc = _make_encounter(events, has_discharge=True, status="closed")
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert len(stage.encounters) == 1
        assert stage.encounters_reconciled == 1

    def test_reconcile_stage_records_metrics(self) -> None:
        """ReconcileStage records stage metrics with correct counts."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        events = [
            _make_event("E1", "ADMIT", base_ts, "adt_vendor_x", patient_class="inpatient"),
            _make_event(
                "E2", "DISCHARGE", base_ts + timedelta(hours=48),
                "adt_vendor_x", patient_class="inpatient",
            ),
        ]

        enc = _make_encounter(events, has_discharge=True, status="closed")
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert stage.metrics.records_in == 1
        assert stage.metrics.records_out == 1
        assert stage.metrics.stage_name == "reconcile"


class TestReconcileStageFlags:
    """Test flag generation in ReconcileStage."""

    def test_flags_generated_tracking(self) -> None:
        """ReconcileStage tracks flag counts by type."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        # Encounter with claims only (no ADT) -> CLAIMS_ONLY_ENCOUNTER
        events = [
            _make_event("E1", "CLAIM_ADMIT", base_ts, "claims_clearinghouse", patient_class="inpatient"),
            _make_event(
                "E2", "CLAIM_DISCHARGE", base_ts + timedelta(hours=48),
                "claims_clearinghouse", patient_class="inpatient",
            ),
        ]

        enc = _make_encounter(events, has_discharge=True, status="closed")
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert "CLAIMS_ONLY_ENCOUNTER" in stage.flags_generated
        assert stage.flags_generated["CLAIMS_ONLY_ENCOUNTER"] >= 1

    def test_auth_without_admit_count(self) -> None:
        """ReconcileStage tracks auth_without_admit_count."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        # Auth-only encounter -> AUTH_WITHOUT_ADMIT
        events = [
            _make_event("E1", "AUTH_REQUESTED", base_ts, "auth_portal"),
        ]

        enc = _make_encounter(events)
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert stage.auth_without_admit_count == 1

    def test_timestamp_mismatch_flag(self) -> None:
        """ReconcileStage flags timestamp mismatches between ADT and claims."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        events = [
            _make_event("E1", "ADMIT", base_ts, "adt_vendor_x", patient_class="inpatient"),
            _make_event(
                "E2", "CLAIM_ADMIT",
                base_ts + timedelta(hours=30),  # >24h diff
                "claims_clearinghouse",
                patient_class="inpatient",
            ),
            _make_event(
                "E3", "DISCHARGE", base_ts + timedelta(hours=72),
                "adt_vendor_x", patient_class="inpatient",
            ),
        ]

        enc = _make_encounter(events, has_discharge=True, status="closed")
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert "TIMESTAMP_MISMATCH" in stage.flags_generated
        assert stage.flags_generated["TIMESTAMP_MISMATCH"] >= 1


class TestReconcileStageMixedSources:
    """Test ReconcileStage with mixed-source encounters."""

    def test_mixed_source_encounter_reconciliation(self) -> None:
        """ReconcileStage correctly reconciles encounter with ADT + claims + auth."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        events = [
            _make_event(
                "E1", "ADMIT", base_ts, "adt_vendor_x",
                patient_class="observation",
                principal_diagnosis="R07.9",
            ),
            _make_event(
                "E2", "CLAIM_ADMIT", base_ts + timedelta(hours=1), "claims_clearinghouse",
                patient_class="inpatient",
                drg="470",
                payer_id="PAYER-001",
                principal_diagnosis="M17.11",
                diagnosis_codes=[{"code": "M17.11", "type": "ICD-10-CM"}],
            ),
            _make_event(
                "E3", "CLAIM_DISCHARGE", base_ts + timedelta(hours=72), "claims_clearinghouse",
                patient_class="inpatient",
            ),
            _make_event(
                "E4", "AUTH_APPROVED", base_ts + timedelta(hours=2), "auth_portal",
            ),
            _make_event(
                "E5", "DISCHARGE", base_ts + timedelta(hours=71), "adt_vendor_x",
                patient_class="inpatient",
            ),
        ]

        enc = _make_encounter(events, has_discharge=True, status="closed")
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert len(stage.encounters) == 1
        reconciled = stage.encounters[0]

        # Timestamps should come from ADT (highest timestamp priority)
        assert reconciled.reconciled_timestamps is not None
        assert reconciled.reconciled_timestamps.admit_source_priority == "adt"

        # Classification should come from claims (highest classification priority)
        assert reconciled.reconciled_classification is not None
        assert reconciled.reconciled_classification.encounter_type == "inpatient"
        assert reconciled.reconciled_classification.drg == "470"

        # No AUTH_WITHOUT_ADMIT since ADT+claims are present
        assert stage.auth_without_admit_count == 0

    def test_reconcile_stage_with_config_overrides(self) -> None:
        """ReconcileStage respects config overrides for priorities and tolerances."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        events = [
            _make_event("E1", "ADMIT", base_ts, "adt_vendor_x", patient_class="inpatient"),
            _make_event(
                "E2", "CLAIM_ADMIT", base_ts + timedelta(hours=30),
                "claims_clearinghouse", patient_class="inpatient",
            ),
        ]

        enc = _make_encounter(events)
        stage = ReconcileStage()
        stage.encounters_in = [enc]

        # Set tolerance to 48h so 30h diff does NOT flag
        config: dict[str, Any] = {
            "reconciliation": {
                "timestamp_tolerance_hours": 48,
            }
        }

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context(config)
        stage.run(batch, context)

        assert "TIMESTAMP_MISMATCH" not in stage.flags_generated

    def test_multiple_encounters_reconciled(self) -> None:
        """ReconcileStage processes multiple encounters correctly."""
        base_ts = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)

        enc1_events = [
            _make_event("E1", "ADMIT", base_ts, "adt_vendor_x", patient_class="inpatient"),
            _make_event(
                "E2", "DISCHARGE", base_ts + timedelta(hours=48),
                "adt_vendor_x", patient_class="inpatient",
            ),
        ]

        enc2_events = [
            _make_event(
                "E3", "CLAIM_ADMIT", base_ts + timedelta(days=10),
                "claims_clearinghouse", patient_class="inpatient",
                patient_key="PAT-002",
            ),
            _make_event(
                "E4", "CLAIM_DISCHARGE", base_ts + timedelta(days=12),
                "claims_clearinghouse", patient_class="inpatient",
                patient_key="PAT-002",
            ),
        ]

        enc1 = _make_encounter(enc1_events, has_discharge=True, status="closed")
        enc2 = _make_encounter(
            enc2_events, patient_key="PAT-002",
            has_discharge=True, status="closed",
        )

        stage = ReconcileStage()
        stage.encounters_in = [enc1, enc2]

        batch = EventBatch(batch_id="batch-001", events=[])
        context = _make_context()
        stage.run(batch, context)

        assert len(stage.encounters) == 2
        assert stage.encounters_reconciled == 2

        # enc2 is claims-only
        assert "CLAIMS_ONLY_ENCOUNTER" in stage.flags_generated
