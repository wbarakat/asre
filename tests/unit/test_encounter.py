"""Tests for Encounter dataclass."""

from datetime import datetime, timezone

from asre.models.encounter import Encounter


class TestEncounter:
    def test_construct_with_all_required_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        encounter = Encounter(
            encounter_id="enc-001",
            patient_key="patient-123",
            encounter_type="inpatient",
            status="open",
            admit_ts=now,
            facility_canonical_id="FAC_001",
            facility_name="St. Mary's Hospital",
            is_acute=True,
            source_event_ids=["evt-001", "evt-002"],
            source_systems=["adt_vendor_x"],
            has_adt=True,
            has_claims=False,
            has_auth=False,
            confidence_score=0.85,
            confidence_flags=["HAS_ADT_ADMIT"],
            created_at=now,
            updated_at=now,
            asre_version="0.1.0",
        )
        assert encounter.encounter_id == "enc-001"
        assert encounter.patient_key == "patient-123"
        assert encounter.encounter_type == "inpatient"
        assert encounter.status == "open"
        assert encounter.admit_ts == now
        assert encounter.facility_canonical_id == "FAC_001"
        assert encounter.facility_name == "St. Mary's Hospital"
        assert encounter.is_acute is True
        assert encounter.source_event_ids == ["evt-001", "evt-002"]
        assert encounter.source_systems == ["adt_vendor_x"]
        assert encounter.has_adt is True
        assert encounter.has_claims is False
        assert encounter.has_auth is False
        assert encounter.confidence_score == 0.85
        assert encounter.confidence_flags == ["HAS_ADT_ADMIT"]
        assert encounter.created_at == now
        assert encounter.updated_at == now
        assert encounter.asre_version == "0.1.0"

    def test_optional_fields_default_to_none(self) -> None:
        now = datetime.now(tz=timezone.utc)
        encounter = Encounter(
            encounter_id="enc-002",
            patient_key="patient-456",
            encounter_type="observation",
            status="closed",
            admit_ts=now,
            facility_canonical_id="FAC_002",
            facility_name="Memorial Hospital",
            is_acute=True,
            source_event_ids=["evt-003"],
            source_systems=["claims"],
            has_adt=False,
            has_claims=True,
            has_auth=False,
            confidence_score=0.60,
            confidence_flags=[],
            created_at=now,
            updated_at=now,
            asre_version="0.1.0",
        )
        assert encounter.discharge_ts is None
        assert encounter.los_hours is None
        assert encounter.admit_source_priority is None
        assert encounter.discharge_source_priority is None
        assert encounter.payer_id is None
        assert encounter.drg is None
        assert encounter.principal_diagnosis is None
        assert encounter.admitting_diagnosis is None
        assert encounter.diagnosis_codes is None
        assert encounter.is_readmission is None
        assert encounter.readmission_days is None
        assert encounter.obs_to_ip_conversion is None
        assert encounter.transfer_chain is None
        assert encounter.episode_id is None

    def test_construct_with_all_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        discharge = datetime(2026, 1, 5, 14, 0, tzinfo=timezone.utc)
        encounter = Encounter(
            encounter_id="enc-003",
            patient_key="patient-789",
            encounter_type="inpatient",
            status="closed",
            admit_ts=now,
            discharge_ts=discharge,
            facility_canonical_id="FAC_001",
            facility_name="Good Samaritan Hospital",
            is_acute=True,
            los_hours=72.0,
            source_event_ids=["evt-010", "evt-011", "evt-012"],
            source_systems=["adt_vendor_x", "claims_clearinghouse"],
            has_adt=True,
            has_claims=True,
            has_auth=True,
            confidence_score=0.95,
            confidence_flags=["HAS_CLAIMS", "HAS_ADT_ADMIT", "HAS_AUTH"],
            admit_source_priority="adt",
            discharge_source_priority="claims",
            payer_id="PAYER-001",
            drg="470",
            principal_diagnosis="J18.9",
            admitting_diagnosis="R06.00",
            diagnosis_codes=[{"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"}],
            is_readmission=True,
            readmission_days=14,
            obs_to_ip_conversion=False,
            transfer_chain=["enc-003", "enc-004"],
            episode_id="ep-001",
            created_at=now,
            updated_at=now,
            asre_version="0.1.0",
        )
        assert encounter.discharge_ts == discharge
        assert encounter.los_hours == 72.0
        assert encounter.admit_source_priority == "adt"
        assert encounter.discharge_source_priority == "claims"
        assert encounter.payer_id == "PAYER-001"
        assert encounter.drg == "470"
        assert encounter.principal_diagnosis == "J18.9"
        assert encounter.admitting_diagnosis == "R06.00"
        assert encounter.diagnosis_codes == [{"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"}]
        assert encounter.is_readmission is True
        assert encounter.readmission_days == 14
        assert encounter.obs_to_ip_conversion is False
        assert encounter.transfer_chain == ["enc-003", "enc-004"]
        assert encounter.episode_id == "ep-001"

    def test_field_types(self) -> None:
        now = datetime.now(tz=timezone.utc)
        encounter = Encounter(
            encounter_id="enc-004",
            patient_key="patient-000",
            encounter_type="ed_only",
            status="closed",
            admit_ts=now,
            discharge_ts=now,
            facility_canonical_id="FAC_003",
            facility_name="Test ED",
            is_acute=False,
            los_hours=4.5,
            source_event_ids=["evt-100"],
            source_systems=["adt"],
            has_adt=True,
            has_claims=False,
            has_auth=False,
            confidence_score=0.50,
            confidence_flags=["HAS_ADT_ADMIT"],
            created_at=now,
            updated_at=now,
            asre_version="0.1.0",
        )
        assert isinstance(encounter.encounter_id, str)
        assert isinstance(encounter.patient_key, str)
        assert isinstance(encounter.encounter_type, str)
        assert isinstance(encounter.status, str)
        assert isinstance(encounter.admit_ts, datetime)
        assert isinstance(encounter.discharge_ts, datetime)
        assert isinstance(encounter.facility_canonical_id, str)
        assert isinstance(encounter.facility_name, str)
        assert isinstance(encounter.is_acute, bool)
        assert isinstance(encounter.los_hours, float)
        assert isinstance(encounter.source_event_ids, list)
        assert isinstance(encounter.source_systems, list)
        assert isinstance(encounter.has_adt, bool)
        assert isinstance(encounter.has_claims, bool)
        assert isinstance(encounter.has_auth, bool)
        assert isinstance(encounter.confidence_score, float)
        assert isinstance(encounter.confidence_flags, list)
        assert isinstance(encounter.created_at, datetime)
        assert isinstance(encounter.updated_at, datetime)
        assert isinstance(encounter.asre_version, str)

    def test_importable_from_models(self) -> None:
        """Verify the import path works as specified in acceptance criteria."""
        from asre.models.encounter import Encounter as Enc
        assert Enc is Encounter
