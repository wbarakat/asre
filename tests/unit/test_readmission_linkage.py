"""Tests for US-087 — Readmission linkage: includes_readmission on episodes.

Verifies that readmissions are linked to the same episode as the index
admission and that the episode group's includes_readmission flag is set.
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.models.encounter import Encounter


def _make_encounter(
    encounter_id: str,
    patient_key: str,
    admit_ts: datetime,
    discharge_ts: datetime | None = None,
    facility_canonical_id: str = "FAC-001",
    encounter_type: str = "inpatient",
    is_acute: bool = True,
    status: str = "closed",
    confidence_score: float = 0.8,
    los_hours: float | None = None,
    is_readmission: bool | None = None,
) -> Encounter:
    """Helper to build minimal Encounter for testing."""
    now = datetime.now(tz=timezone.utc)
    if los_hours is None and discharge_ts is not None:
        los_hours = (discharge_ts - admit_ts).total_seconds() / 3600
    return Encounter(
        encounter_id=encounter_id,
        patient_key=patient_key,
        encounter_type=encounter_type,
        status=status,
        admit_ts=admit_ts,
        facility_canonical_id=facility_canonical_id,
        facility_name="TEST FACILITY",
        is_acute=is_acute,
        source_event_ids=["evt-1"],
        source_systems=["adt_test"],
        has_adt=True,
        has_claims=False,
        has_auth=False,
        confidence_score=confidence_score,
        confidence_flags=[],
        created_at=now,
        updated_at=now,
        asre_version="0.1.0",
        discharge_ts=discharge_ts,
        los_hours=los_hours,
        is_readmission=is_readmission,
    )


class TestReadmissionLinkageMetadata:
    """US-087: Readmission linkage sets includes_readmission on episode group."""

    def test_readmission_within_window_same_episode(self) -> None:
        """Acute discharge Jan 1, acute admit Jan 15 -> same episode."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            is_readmission=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 1
        assert set(episodes[0].encounter_ids) == {"enc-1", "enc-2"}
        assert episodes[0].includes_readmission is True

    def test_readmission_outside_window_separate_episodes(self) -> None:
        """Acute discharge Jan 1, acute admit Feb 15 -> separate episodes (>30 days)."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            facility_canonical_id="FAC-001",
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 2, 18, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            facility_canonical_id="FAC-002",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2
        # Neither episode should have readmission flag
        assert episodes[0].includes_readmission is False
        assert episodes[1].includes_readmission is False

    def test_both_must_be_acute(self) -> None:
        """Acute discharge Jan 1, SNF admit Jan 5 -> NOT a readmission (SNF not acute).

        This should link via post-acute rule instead, not readmission.
        """
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 8, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 20, 14, 0, tzinfo=timezone.utc),
            is_acute=False,
            facility_canonical_id="FAC-SNF",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        # Linked via post-acute, NOT readmission
        assert len(episodes) == 1
        assert episodes[0].includes_readmission is False

    def test_first_admission_never_readmission(self) -> None:
        """A single encounter episode should not have includes_readmission=True."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1])

        assert len(episodes) == 1
        assert episodes[0].includes_readmission is False

    def test_readmission_exactly_at_boundary(self) -> None:
        """Acute admit exactly 30 days after prior acute discharge -> same episode."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        # Exactly 30 days after discharge
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 2, 4, 14, 0, tzinfo=timezone.utc),
            datetime(2024, 2, 8, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            is_readmission=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 1
        assert episodes[0].includes_readmission is True

    def test_chain_with_readmission(self) -> None:
        """Readmission in a multi-encounter chain sets includes_readmission."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        # Readmission 10 days later
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 20, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            is_readmission=True,
        )
        # Post-acute 5 days after second discharge
        enc3 = _make_encounter(
            "enc-3",
            "PAT-A",
            datetime(2024, 1, 25, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 2, 10, 14, 0, tzinfo=timezone.utc),
            is_acute=False,
            facility_canonical_id="FAC-SNF",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2, enc3])

        assert len(episodes) == 1
        assert episodes[0].includes_readmission is True
