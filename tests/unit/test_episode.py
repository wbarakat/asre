"""Tests for Episode dataclass."""

from datetime import datetime, timezone

from asre.models.episode import Episode


class TestEpisode:
    def test_construct_with_all_required_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        episode = Episode(
            episode_id="ep-001",
            patient_key="patient-123",
            episode_type="surgical",
            episode_status="closed",
            episode_start_ts=now,
            encounter_ids=["enc-001", "enc-002"],
            encounter_count=2,
            facility_count=1,
            facility_sequence=["FAC_001"],
            is_acute=True,
            confidence_score=0.85,
            created_at=now,
            updated_at=now,
        )
        assert episode.episode_id == "ep-001"
        assert episode.patient_key == "patient-123"
        assert episode.episode_type == "surgical"
        assert episode.episode_status == "closed"
        assert episode.episode_start_ts == now
        assert episode.encounter_ids == ["enc-001", "enc-002"]
        assert episode.encounter_count == 2
        assert episode.facility_count == 1
        assert episode.facility_sequence == ["FAC_001"]
        assert episode.is_acute is True
        assert episode.confidence_score == 0.85
        assert episode.created_at == now
        assert episode.updated_at == now

    def test_optional_fields_default_to_none(self) -> None:
        now = datetime.now(tz=timezone.utc)
        episode = Episode(
            episode_id="ep-002",
            patient_key="patient-456",
            episode_type="medical",
            episode_status="active",
            episode_start_ts=now,
            encounter_ids=["enc-003"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_002"],
            is_acute=True,
            confidence_score=0.70,
            created_at=now,
            updated_at=now,
        )
        assert episode.episode_end_ts is None
        assert episode.total_los_days is None
        assert episode.includes_readmission is None
        assert episode.includes_post_acute is None
        assert episode.principal_diagnosis is None
        assert episode.diagnosis_codes is None

    def test_construct_with_all_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        end_ts = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)
        episode = Episode(
            episode_id="ep-003",
            patient_key="patient-789",
            episode_type="surgical",
            episode_status="closed",
            episode_start_ts=now,
            episode_end_ts=end_ts,
            total_los_days=14.5,
            encounter_ids=["enc-010", "enc-011", "enc-012"],
            encounter_count=3,
            facility_count=2,
            facility_sequence=["FAC_001", "FAC_002"],
            includes_readmission=True,
            includes_post_acute=True,
            is_acute=True,
            principal_diagnosis="M17.11",
            diagnosis_codes=[
                {"code": "M17.11", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"},
            ],
            confidence_score=0.92,
            created_at=now,
            updated_at=now,
        )
        assert episode.episode_end_ts == end_ts
        assert episode.total_los_days == 14.5
        assert episode.includes_readmission is True
        assert episode.includes_post_acute is True
        assert episode.principal_diagnosis == "M17.11"
        assert episode.diagnosis_codes == [
            {"code": "M17.11", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"},
        ]

    def test_field_types(self) -> None:
        now = datetime.now(tz=timezone.utc)
        episode = Episode(
            episode_id="ep-004",
            patient_key="patient-000",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=now,
            episode_end_ts=now,
            total_los_days=3.0,
            encounter_ids=["enc-100"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_003"],
            includes_readmission=False,
            includes_post_acute=False,
            is_acute=False,
            principal_diagnosis="J18.9",
            diagnosis_codes=[],
            confidence_score=0.50,
            created_at=now,
            updated_at=now,
        )
        assert isinstance(episode.episode_id, str)
        assert isinstance(episode.patient_key, str)
        assert isinstance(episode.episode_type, str)
        assert isinstance(episode.episode_status, str)
        assert isinstance(episode.episode_start_ts, datetime)
        assert isinstance(episode.episode_end_ts, datetime)
        assert isinstance(episode.total_los_days, float)
        assert isinstance(episode.encounter_ids, list)
        assert isinstance(episode.encounter_count, int)
        assert isinstance(episode.facility_count, int)
        assert isinstance(episode.facility_sequence, list)
        assert isinstance(episode.includes_readmission, bool)
        assert isinstance(episode.includes_post_acute, bool)
        assert isinstance(episode.is_acute, bool)
        assert isinstance(episode.principal_diagnosis, str)
        assert isinstance(episode.diagnosis_codes, list)
        assert isinstance(episode.confidence_score, float)
        assert isinstance(episode.created_at, datetime)
        assert isinstance(episode.updated_at, datetime)

    def test_importable_from_models(self) -> None:
        """Verify the import path works as specified in acceptance criteria."""
        from asre.models.episode import Episode as Ep
        assert Ep is Episode
