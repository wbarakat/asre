"""Tests for Reconciler — timestamp and classification reconciliation (US-058, US-059)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from asre.models.canonical_event import CanonicalEvent
from asre.reconcile.reconciler import Reconciler, ReconciledClassification
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


def _make_encounter(events: list[CanonicalEvent]) -> StitchedEncounter:
    """Helper to build a StitchedEncounter from events."""
    enc = StitchedEncounter(
        patient_key=events[0].patient_key,
        facility_canonical_id=events[0].facility_canonical_id,
    )
    for event in events:
        enc.add_event(event)
    enc.generate_encounter_id()
    return enc


class TestTimestampSelectionBySourcePriority:
    """US-058: admit_ts and discharge_ts selected from most trusted source."""

    def test_admit_ts_from_highest_priority_source(self) -> None:
        """ADT admit (priority 100) beats claims admit (priority 80)."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-003",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit, adt_discharge])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        # ADT has priority 100 > claims priority 80, so ADT's admit_ts is used
        assert result.admit_ts == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert result.admit_source_priority == "adt"

    def test_discharge_ts_from_highest_priority_source(self) -> None:
        """ADT discharge (priority 100) beats claims discharge (priority 80)."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_discharge = _make_event(
            event_id="evt-002",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 18, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-003",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_discharge, adt_discharge])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        # ADT discharge used (priority 100 > claims 80)
        assert result.discharge_ts == datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc)
        assert result.discharge_source_priority == "adt"

    def test_claims_used_when_no_adt(self) -> None:
        """When only claims source exists, claims timestamps are used."""
        claims_admit = _make_event(
            event_id="evt-001",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_discharge = _make_event(
            event_id="evt-002",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 18, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        enc = _make_encounter([claims_admit, claims_discharge])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        assert result.admit_ts == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert result.admit_source_priority == "claims"
        assert result.discharge_ts == datetime(2024, 1, 18, 15, 0, tzinfo=timezone.utc)
        assert result.discharge_source_priority == "claims"

    def test_custom_timestamp_priority(self) -> None:
        """Custom priority config is respected."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        # Reverse priority: claims > adt
        reconciler = Reconciler(
            timestamp_priority={"claims": 100, "adt": 80, "auth": 40}
        )
        result = reconciler.reconcile_timestamps(enc)

        # Claims should win with custom priority
        assert result.admit_ts == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert result.admit_source_priority == "claims"

    def test_open_encounter_no_discharge(self) -> None:
        """Open encounter has no discharge_ts and no discharge_source_priority."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        assert result.admit_ts == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert result.admit_source_priority == "adt"
        assert result.discharge_ts is None
        assert result.discharge_source_priority is None

    def test_auth_lowest_priority_for_timestamps(self) -> None:
        """Auth events have lowest timestamp priority (40 by default)."""
        auth_admit = _make_event(
            event_id="evt-001",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([auth_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_timestamps(enc)

        # Claims (80) > auth (40), so claims timestamp is used
        assert result.admit_ts == datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc)
        assert result.admit_source_priority == "claims"


class TestClassificationResolutionBySourcePriority:
    """US-059: encounter_type, DRG, payer, diagnoses from most trusted classification source."""

    def test_encounter_type_from_claims_over_adt(self) -> None:
        """Claims classification priority (100) beats ADT (80).
        ADT says observation, claims says inpatient -> inpatient."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="observation",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        assert result.encounter_type == "inpatient"

    def test_drg_from_claims_when_available(self) -> None:
        """DRG is set from claims when available."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
            drg="470",
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        assert result.drg == "470"

    def test_payer_id_from_highest_classification_priority(self) -> None:
        """Payer is set from highest classification priority source."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
            payer_id="PAYER-ADT",
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
            payer_id="PAYER-CLAIMS",
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        # Claims has classification_priority 100 > ADT 80
        assert result.payer_id == "PAYER-CLAIMS"

    def test_principal_diagnosis_from_claims(self) -> None:
        """Principal diagnosis is set from claims when available."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
            principal_diagnosis="J18.9",
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
            principal_diagnosis="J18.1",
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        # Claims has higher classification priority
        assert result.principal_diagnosis == "J18.1"

    def test_admitting_diagnosis_from_adt(self) -> None:
        """Admitting diagnosis is set from ADT when available."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
            principal_diagnosis="R07.9",
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
            principal_diagnosis="I21.0",
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        # Admitting diagnosis comes from ADT specifically
        assert result.admitting_diagnosis == "R07.9"

    def test_diagnosis_codes_aggregated_claims_precedence(self) -> None:
        """Diagnosis codes aggregated from all sources with claims taking precedence."""
        adt_codes = [{"code": "R07.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"}]
        claims_codes = [
            {"code": "I21.0", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"},
            {"code": "I25.10", "type": "ICD-10-CM", "sequence": 2, "poa": "Y"},
        ]
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
            diagnosis_codes=adt_codes,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
            diagnosis_codes=claims_codes,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        # Claims codes come first (higher priority), then unique ADT codes
        codes = [d["code"] for d in result.diagnosis_codes]
        assert "I21.0" in codes
        assert "I25.10" in codes
        assert "R07.9" in codes
        # Claims codes should appear before ADT-only codes
        assert codes.index("I21.0") < codes.index("R07.9")

    def test_encounter_type_adt_only(self) -> None:
        """When only ADT events exist, encounter_type from ADT patient_class."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="observation",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        assert result.encounter_type == "observation"

    def test_auth_not_overriding_classification(self) -> None:
        """Auth has lowest classification priority (40), does not override ADT or claims."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
            payer_id="PAYER-ADT",
        )
        auth_event = _make_event(
            event_id="evt-002",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 14, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
            payer_id="PAYER-AUTH",
        )
        enc = _make_encounter([adt_admit, auth_event])

        reconciler = Reconciler()
        result = reconciler.reconcile_classification(enc)

        # ADT (80) > auth (40) for classification
        assert result.encounter_type == "inpatient"
        assert result.payer_id == "PAYER-ADT"
