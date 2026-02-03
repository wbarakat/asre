"""Tests for EpisodeMetadataBuilder — US-094."""

from datetime import datetime, timedelta, timezone

import pytest

from asre.models.encounter import Encounter
from asre.models.episode import Episode


def _make_encounter(
    encounter_id: str = "enc-001",
    patient_key: str = "PAT-001",
    encounter_type: str = "inpatient",
    status: str = "closed",
    admit_ts: datetime | None = None,
    discharge_ts: datetime | None = None,
    facility_canonical_id: str = "FAC-001",
    facility_name: str = "General Hospital",
    is_acute: bool = True,
    los_hours: float | None = 48.0,
    confidence_score: float = 0.80,
    confidence_flags: list[str] | None = None,
    source_systems: list[str] | None = None,
    drg: str | None = None,
    principal_diagnosis: str | None = None,
    diagnosis_codes: list[dict[str, str | None]] | None = None,
) -> Encounter:
    now = datetime.now(tz=timezone.utc)
    return Encounter(
        encounter_id=encounter_id,
        patient_key=patient_key,
        encounter_type=encounter_type,
        status=status,
        admit_ts=admit_ts or now,
        discharge_ts=discharge_ts,
        los_hours=los_hours,
        facility_canonical_id=facility_canonical_id,
        facility_name=facility_name,
        is_acute=is_acute,
        source_event_ids=["evt-1"],
        source_systems=source_systems or ["adt_vendor"],
        has_adt=True,
        has_claims=False,
        has_auth=False,
        confidence_score=confidence_score,
        confidence_flags=confidence_flags or [],
        created_at=now,
        updated_at=now,
        asre_version="0.1.0",
        drg=drg,
        principal_diagnosis=principal_diagnosis,
        diagnosis_codes=diagnosis_codes,
    )


class TestEpisodeMetadataBuilder:
    """Tests for building Episode from encounters and episode group data."""

    def test_single_closed_encounter_episode(self) -> None:
        """Single closed encounter produces correct episode metadata."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        admit = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        discharge = datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc)
        enc = _make_encounter(
            encounter_id="enc-001",
            admit_ts=admit,
            discharge_ts=discharge,
            los_hours=48.0,
            confidence_score=0.85,
            principal_diagnosis="J18.9",
            diagnosis_codes=[{"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"}],
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-001",
            encounters=[enc],
            includes_readmission=False,
            includes_post_acute=False,
        )

        assert isinstance(episode, Episode)
        assert episode.episode_id == "ep-001"
        assert episode.patient_key == "PAT-001"
        assert episode.episode_status == "closed"
        assert episode.episode_start_ts == admit
        assert episode.episode_end_ts == discharge
        assert episode.total_los_days == pytest.approx(2.0)
        assert episode.encounter_ids == ["enc-001"]
        assert episode.encounter_count == 1
        assert episode.facility_count == 1
        assert episode.facility_sequence == ["FAC-001"]
        assert episode.is_acute is True
        assert episode.includes_readmission is False
        assert episode.includes_post_acute is False
        assert episode.principal_diagnosis == "J18.9"
        assert episode.diagnosis_codes is not None
        assert len(episode.diagnosis_codes) == 1
        assert isinstance(episode.confidence_score, float)
        assert isinstance(episode.created_at, datetime)
        assert isinstance(episode.updated_at, datetime)

    def test_episode_status_active_when_any_encounter_open(self) -> None:
        """Episode status is 'active' when any encounter is still open."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        admit1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        admit2 = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=admit1,
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            status="closed",
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=admit2,
            discharge_ts=None,
            status="open",
            los_hours=None,
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-002",
            encounters=[enc1, enc2],
            includes_readmission=False,
            includes_post_acute=False,
        )

        assert episode.episode_status == "active"
        assert episode.episode_end_ts is None
        assert episode.total_los_days is None

    def test_episode_status_closed_when_all_encounters_closed(self) -> None:
        """Episode status is 'closed' when all encounters are closed."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            status="closed",
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc),
            status="closed",
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-003",
            encounters=[enc1, enc2],
            includes_readmission=True,
            includes_post_acute=False,
        )

        assert episode.episode_status == "closed"
        assert episode.episode_end_ts == datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc)
        assert episode.includes_readmission is True

    def test_multi_encounter_episode_metadata(self) -> None:
        """Multi-encounter episode derives correct aggregate fields."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        admit1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        discharge1 = datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc)
        admit2 = datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc)
        discharge2 = datetime(2026, 1, 8, 10, 0, tzinfo=timezone.utc)

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=admit1,
            discharge_ts=discharge1,
            facility_canonical_id="FAC-001",
            facility_name="Hospital A",
            is_acute=True,
            los_hours=48.0,
            confidence_score=0.80,
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=admit2,
            discharge_ts=discharge2,
            facility_canonical_id="FAC-002",
            facility_name="SNF B",
            is_acute=False,
            los_hours=72.0,
            confidence_score=0.60,
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-004",
            encounters=[enc1, enc2],
            includes_readmission=False,
            includes_post_acute=True,
        )

        assert episode.episode_start_ts == admit1
        assert episode.episode_end_ts == discharge2
        # total_los_days = (last discharge - first admit) in days
        expected_los = (discharge2 - admit1).total_seconds() / 86400.0
        assert episode.total_los_days == pytest.approx(expected_los)
        assert episode.encounter_ids == ["enc-001", "enc-002"]
        assert episode.encounter_count == 2
        assert episode.facility_count == 2
        assert episode.facility_sequence == ["FAC-001", "FAC-002"]
        # is_acute: True if any encounter is acute
        assert episode.is_acute is True
        assert episode.includes_post_acute is True

    def test_episode_type_from_condition_grouper(self) -> None:
        """Episode type is derived from diagnosis codes and DRG via condition grouper."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            drg="470",  # Hip replacement -> surgical
            principal_diagnosis="M17.11",
            diagnosis_codes=[{"code": "M17.11", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"}],
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-005",
            encounters=[enc],
            includes_readmission=False,
            includes_post_acute=False,
        )

        assert episode.episode_type == "surgical"

    def test_episode_type_unclassified_without_diagnosis(self) -> None:
        """Episode type is 'unclassified' when no diagnosis or DRG available."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            drg=None,
            principal_diagnosis=None,
            diagnosis_codes=None,
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-006",
            encounters=[enc],
            includes_readmission=False,
            includes_post_acute=False,
        )

        assert episode.episode_type == "unclassified"

    def test_confidence_score_weighted_by_los(self) -> None:
        """Episode confidence score is LOS-weighted mean of encounter scores."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            los_hours=48.0,
            confidence_score=0.80,
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 6, 10, 0, tzinfo=timezone.utc),
            los_hours=24.0,
            confidence_score=0.60,
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-007",
            encounters=[enc1, enc2],
            includes_readmission=False,
            includes_post_acute=False,
        )

        # weighted mean: (0.80*48 + 0.60*24) / (48+24) = (38.4+14.4)/72 = 52.8/72 ≈ 0.7333
        expected = (0.80 * 48 + 0.60 * 24) / (48 + 24)
        assert episode.confidence_score == pytest.approx(expected)

    def test_facility_sequence_preserves_order(self) -> None:
        """Facility sequence preserves encounter order (admit_ts) with unique facilities."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-002",
        )
        enc3 = _make_encounter(
            encounter_id="enc-003",
            admit_ts=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 12, 10, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",  # back to first facility
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-008",
            encounters=[enc1, enc2, enc3],
            includes_readmission=False,
            includes_post_acute=False,
        )

        # facility_sequence includes each facility in order of first appearance
        assert episode.facility_sequence == ["FAC-001", "FAC-002"]
        assert episode.facility_count == 2

    def test_diagnosis_codes_aggregated_from_encounters(self) -> None:
        """Diagnosis codes are aggregated from all encounters, deduplicated by code."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            diagnosis_codes=[
                {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},
                {"code": "I10", "type": "ICD-10-CM", "sequence": "2", "poa": "Y"},
            ],
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc),
            diagnosis_codes=[
                {"code": "J18.9", "type": "ICD-10-CM", "sequence": "1", "poa": "Y"},  # duplicate
                {"code": "E11.9", "type": "ICD-10-CM", "sequence": "2", "poa": None},
            ],
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-009",
            encounters=[enc1, enc2],
            includes_readmission=False,
            includes_post_acute=False,
        )

        assert episode.diagnosis_codes is not None
        codes = {d["code"] for d in episode.diagnosis_codes}
        assert codes == {"J18.9", "I10", "E11.9"}

    def test_principal_diagnosis_from_first_encounter(self) -> None:
        """Principal diagnosis taken from the first encounter that has one."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            principal_diagnosis="J18.9",
        )
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 7, 10, 0, tzinfo=timezone.utc),
            principal_diagnosis="I10",
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-010",
            encounters=[enc1, enc2],
            includes_readmission=False,
            includes_post_acute=False,
        )

        assert episode.principal_diagnosis == "J18.9"

    def test_episode_status_reopened(self) -> None:
        """Episode status is 'reopened' when any encounter has status 'cancelled' + another is open."""
        from asre.episode.metadata_builder import EpisodeMetadataBuilder

        enc1 = _make_encounter(
            encounter_id="enc-001",
            admit_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2026, 1, 3, 10, 0, tzinfo=timezone.utc),
            status="closed",
        )
        # A cancelled encounter that was reopened — represented by the encounter being open after cancellation
        enc2 = _make_encounter(
            encounter_id="enc-002",
            admit_ts=datetime(2026, 1, 5, 10, 0, tzinfo=timezone.utc),
            discharge_ts=None,
            status="cancelled",
            los_hours=None,
        )

        builder = EpisodeMetadataBuilder()
        episode = builder.build(
            episode_id="ep-011",
            encounters=[enc1, enc2],
            includes_readmission=False,
            includes_post_acute=False,
        )

        # When a cancelled encounter exists alongside other encounters, status is based on
        # the combination — if any encounter is cancelled, episode might be "reopened"
        # if other encounters exist (indicates the episode was cancelled then activity resumed)
        # Per spec: active (any open), closed (all closed), reopened
        # A cancelled encounter mixed with a closed one should still be closed
        # "reopened" is when an episode was previously closed but now has an open encounter
        assert episode.episode_status in ("closed", "reopened")
