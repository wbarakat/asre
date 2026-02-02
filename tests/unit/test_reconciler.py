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


class TestAuthReconciliationRules:
    """US-060: Auth signals validate encounters without anchoring them."""

    def test_auth_does_not_override_adt_fields(self) -> None:
        """Encounter with auth + ADT produces auth not overriding any fields."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
            payer_id="PAYER-ADT",
            principal_diagnosis="J18.9",
        )
        adt_discharge = _make_event(
            event_id="evt-002",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        auth_event = _make_event(
            event_id="evt-003",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 14, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
            payer_id="PAYER-AUTH",
            principal_diagnosis="Z00.0",
        )
        enc = _make_encounter([adt_admit, adt_discharge, auth_event])

        reconciler = Reconciler()

        # Timestamps: ADT should win over auth
        ts_result = reconciler.reconcile_timestamps(enc)
        assert ts_result.admit_ts == datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        assert ts_result.admit_source_priority == "adt"
        assert ts_result.discharge_ts == datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc)
        assert ts_result.discharge_source_priority == "adt"

        # Classification: ADT should win over auth
        cls_result = reconciler.reconcile_classification(enc)
        assert cls_result.encounter_type == "inpatient"
        assert cls_result.payer_id == "PAYER-ADT"
        assert cls_result.principal_diagnosis == "J18.9"

    def test_auth_with_matching_encounter_no_flag(self) -> None:
        """Auth event with a matching encounter should not produce AUTH_WITHOUT_ADMIT flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        auth_event = _make_event(
            event_id="evt-002",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 14, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        enc = _make_encounter([adt_admit, auth_event])

        reconciler = Reconciler()
        flags = reconciler.reconcile_auth(enc)

        assert "AUTH_WITHOUT_ADMIT" not in flags

    def test_orphan_auth_produces_flag(self) -> None:
        """Auth-only encounter (no ADT or claims) produces AUTH_WITHOUT_ADMIT flag."""
        auth_event = _make_event(
            event_id="evt-001",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 14, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        enc = _make_encounter([auth_event])

        reconciler = Reconciler()
        flags = reconciler.reconcile_auth(enc)

        assert "AUTH_WITHOUT_ADMIT" in flags

    def test_auth_only_with_multiple_auth_events_produces_flag(self) -> None:
        """Encounter with only auth events (no ADT/claims) produces AUTH_WITHOUT_ADMIT."""
        auth1 = _make_event(
            event_id="evt-001",
            event_type="AUTH_REQUESTED",
            event_ts=datetime(2024, 1, 14, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        auth2 = _make_event(
            event_id="evt-002",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        enc = _make_encounter([auth1, auth2])

        reconciler = Reconciler()
        flags = reconciler.reconcile_auth(enc)

        assert "AUTH_WITHOUT_ADMIT" in flags

    def test_auth_with_claims_no_flag(self) -> None:
        """Auth event alongside claims (no ADT) should not produce AUTH_WITHOUT_ADMIT."""
        claims_admit = _make_event(
            event_id="evt-001",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        auth_event = _make_event(
            event_id="evt-002",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 14, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        enc = _make_encounter([claims_admit, auth_event])

        reconciler = Reconciler()
        flags = reconciler.reconcile_auth(enc)

        assert "AUTH_WITHOUT_ADMIT" not in flags


class TestMissingDischargeFlag:
    """US-062: MISSING_DISCHARGE flag when admit present but no discharge and open > 48h."""

    def test_open_encounter_over_48h_produces_flag(self) -> None:
        """Admit at Jan 1 10:00, current time Jan 5 -> open > 48h -> MISSING_DISCHARGE."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit])

        reconciler = Reconciler()
        now = datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_missing_discharge(enc, now=now)

        assert "MISSING_DISCHARGE" in flags

    def test_open_encounter_under_48h_no_flag(self) -> None:
        """Admit at Jan 1 10:00, current time Jan 2 -> open < 48h -> no flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit])

        reconciler = Reconciler()
        now = datetime(2024, 1, 2, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_missing_discharge(enc, now=now)

        assert "MISSING_DISCHARGE" not in flags

    def test_closed_encounter_no_flag(self) -> None:
        """Encounter with discharge event should not produce MISSING_DISCHARGE."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-002",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, adt_discharge])

        reconciler = Reconciler()
        now = datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_missing_discharge(enc, now=now)

        assert "MISSING_DISCHARGE" not in flags

    def test_claims_only_open_over_48h_produces_flag(self) -> None:
        """Claims admit with no discharge, open > 48h -> MISSING_DISCHARGE."""
        claims_admit = _make_event(
            event_id="evt-001",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([claims_admit])

        reconciler = Reconciler()
        now = datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_missing_discharge(enc, now=now)

        assert "MISSING_DISCHARGE" in flags


class TestOrphanDischargeFlag:
    """US-062: ORPHAN_DISCHARGE flag when discharge event with no matching admit."""

    def test_discharge_only_produces_flag(self) -> None:
        """Encounter with only a discharge event -> ORPHAN_DISCHARGE."""
        discharge = _make_event(
            event_id="evt-001",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_orphan_discharge(enc)

        assert "ORPHAN_DISCHARGE" in flags

    def test_admit_and_discharge_no_flag(self) -> None:
        """Encounter with both admit and discharge -> no ORPHAN_DISCHARGE."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-002",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, adt_discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_orphan_discharge(enc)

        assert "ORPHAN_DISCHARGE" not in flags

    def test_claims_discharge_without_claims_admit_produces_flag(self) -> None:
        """CLAIM_DISCHARGE without any admit-type event -> ORPHAN_DISCHARGE."""
        claims_discharge = _make_event(
            event_id="evt-001",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        enc = _make_encounter([claims_discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_orphan_discharge(enc)

        assert "ORPHAN_DISCHARGE" in flags

    def test_supporting_event_with_discharge_no_admit_produces_flag(self) -> None:
        """Discharge + supporting event (non-admit) -> ORPHAN_DISCHARGE."""
        supporting = _make_event(
            event_id="evt-001",
            event_type="TRANSFER_IN",
            event_ts=datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
        )
        discharge = _make_event(
            event_id="evt-002",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([supporting, discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_orphan_discharge(enc)

        assert "ORPHAN_DISCHARGE" in flags


class TestClaimsOnlyEncounterFlag:
    """US-062: CLAIMS_ONLY_ENCOUNTER flag when encounter has claims but zero ADT."""

    def test_claims_only_produces_flag(self) -> None:
        """Encounter with only claims events -> CLAIMS_ONLY_ENCOUNTER."""
        claims_admit = _make_event(
            event_id="evt-001",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_discharge = _make_event(
            event_id="evt-002",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        enc = _make_encounter([claims_admit, claims_discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_claims_only(enc)

        assert "CLAIMS_ONLY_ENCOUNTER" in flags

    def test_claims_and_adt_no_flag(self) -> None:
        """Encounter with both claims and ADT events -> no flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        flags = reconciler.flag_claims_only(enc)

        assert "CLAIMS_ONLY_ENCOUNTER" not in flags

    def test_claims_and_auth_still_flags(self) -> None:
        """Encounter with claims + auth but no ADT -> CLAIMS_ONLY_ENCOUNTER."""
        claims_admit = _make_event(
            event_id="evt-001",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        auth_event = _make_event(
            event_id="evt-002",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        enc = _make_encounter([claims_admit, auth_event])

        reconciler = Reconciler()
        flags = reconciler.flag_claims_only(enc)

        assert "CLAIMS_ONLY_ENCOUNTER" in flags


class TestAdtOnlyEncounterFlag:
    """US-062: ADT_ONLY_ENCOUNTER flag when ADT events but zero claims beyond claims lag."""

    def test_adt_only_beyond_claims_lag_produces_flag(self) -> None:
        """ADT-only encounter, admit Jan 1, now Mar 1 (>45 day lag) -> ADT_ONLY_ENCOUNTER."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-002",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, adt_discharge])

        reconciler = Reconciler()
        now = datetime(2024, 3, 1, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_adt_only(enc, now=now, claims_lag_days=45)

        assert "ADT_ONLY_ENCOUNTER" in flags

    def test_adt_only_within_claims_lag_no_flag(self) -> None:
        """ADT-only encounter, admit Jan 1, now Jan 20 (<45 day lag) -> no flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit])

        reconciler = Reconciler()
        now = datetime(2024, 1, 20, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_adt_only(enc, now=now, claims_lag_days=45)

        assert "ADT_ONLY_ENCOUNTER" not in flags

    def test_adt_and_claims_no_flag(self) -> None:
        """Encounter with both ADT and claims -> no flag regardless of age."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        now = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_adt_only(enc, now=now, claims_lag_days=45)

        assert "ADT_ONLY_ENCOUNTER" not in flags

    def test_auth_only_no_flag(self) -> None:
        """Auth-only encounter should not produce ADT_ONLY_ENCOUNTER."""
        auth_event = _make_event(
            event_id="evt-001",
            event_type="AUTH_APPROVED",
            event_ts=datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc),
            source_system="auth_portal",
        )
        enc = _make_encounter([auth_event])

        reconciler = Reconciler()
        now = datetime(2024, 6, 1, 10, 0, tzinfo=timezone.utc)
        flags = reconciler.flag_adt_only(enc, now=now, claims_lag_days=45)

        assert "ADT_ONLY_ENCOUNTER" not in flags


class TestFlagEventPatternsIntegration:
    """US-062: All flags are added to encounter's confidence_flags array."""

    def test_multiple_flags_combined(self) -> None:
        """Encounter can have multiple flags from different checks."""
        # Claims-only encounter with orphan discharge (no admit event)
        claims_discharge = _make_event(
            event_id="evt-001",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        enc = _make_encounter([claims_discharge])

        reconciler = Reconciler()
        flags: list[str] = []
        flags.extend(reconciler.flag_orphan_discharge(enc))
        flags.extend(reconciler.flag_claims_only(enc))

        assert "ORPHAN_DISCHARGE" in flags
        assert "CLAIMS_ONLY_ENCOUNTER" in flags


class TestTimestampMismatchFlag:
    """US-061: Flag timestamp mismatches between ADT and claims sources."""

    def test_mismatch_above_tolerance_produces_flag(self) -> None:
        """ADT admit 10:00 Jan 1, claims admit 15:00 Jan 2 (29h diff) with tolerance 24h -> TIMESTAMP_MISMATCH."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        flags = reconciler.flag_timestamp_mismatches(enc, timestamp_tolerance_hours=24)

        assert "TIMESTAMP_MISMATCH" in flags

    def test_no_mismatch_within_tolerance(self) -> None:
        """ADT admit 10:00, claims admit 11:00 (1h diff) -> no flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        flags = reconciler.flag_timestamp_mismatches(enc, timestamp_tolerance_hours=24)

        assert "TIMESTAMP_MISMATCH" not in flags

    def test_discharge_mismatch_also_flags(self) -> None:
        """Discharge timestamps that differ beyond tolerance also produce flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 30, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-003",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        claims_discharge = _make_event(
            event_id="evt-004",
            event_type="CLAIM_DISCHARGE",
            event_ts=datetime(2024, 1, 6, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit, adt_discharge, claims_discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_timestamp_mismatches(enc, timestamp_tolerance_hours=24)

        assert "TIMESTAMP_MISMATCH" in flags

    def test_custom_tolerance(self) -> None:
        """Custom tolerance is respected — 29h diff with tolerance 48h -> no flag."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        claims_admit = _make_event(
            event_id="evt-002",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 2, 15, 0, tzinfo=timezone.utc),
            source_system="claims_clearinghouse",
            patient_class="inpatient",
            admit_flag=True,
        )
        enc = _make_encounter([adt_admit, claims_admit])

        reconciler = Reconciler()
        flags = reconciler.flag_timestamp_mismatches(enc, timestamp_tolerance_hours=48)

        assert "TIMESTAMP_MISMATCH" not in flags

    def test_single_source_no_flag(self) -> None:
        """Encounter with only one source type cannot have timestamp mismatch."""
        adt_admit = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            patient_class="inpatient",
            admit_flag=True,
        )
        adt_discharge = _make_event(
            event_id="evt-002",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 5, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            discharge_flag=True,
        )
        enc = _make_encounter([adt_admit, adt_discharge])

        reconciler = Reconciler()
        flags = reconciler.flag_timestamp_mismatches(enc, timestamp_tolerance_hours=24)

        assert "TIMESTAMP_MISMATCH" not in flags
