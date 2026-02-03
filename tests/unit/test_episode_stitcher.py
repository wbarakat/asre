"""Tests for EpisodeStitcher — US-086.

Verifies episode stitching algorithm: grouping encounters into episodes
based on temporal and clinical linkage rules.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

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


# ---------------------------------------------------------------------------
# Core algorithm: partition by patient, sort by admit_ts
# ---------------------------------------------------------------------------


class TestBasicStitching:
    """Test basic episode grouping: partition by patient, sort by admit_ts."""

    def test_single_encounter_creates_single_episode(self) -> None:
        """One encounter produces one episode."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc])

        assert len(episodes) == 1
        assert episodes[0].patient_key == "PAT-A"
        assert episodes[0].encounter_ids == ["enc-1"]

    def test_unrelated_encounters_separate_episodes(self) -> None:
        """Encounters far apart for the same patient produce separate episodes."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
        )
        # 6 months later -- no linkage rule should fire
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 7, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 7, 5, 14, 0, tzinfo=timezone.utc),
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2

    def test_different_patients_separate_episodes(self) -> None:
        """Encounters for different patients are always in separate episodes."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-B",
            datetime(2024, 1, 3, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 7, 14, 0, tzinfo=timezone.utc),
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2
        patient_keys = {ep.patient_key for ep in episodes}
        assert patient_keys == {"PAT-A", "PAT-B"}

    def test_encounters_sorted_by_admit_ts(self) -> None:
        """Encounters are processed in admit_ts order regardless of input order."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc_later = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 10, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 12, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-002",
        )
        enc_earlier = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 3, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
        )
        # enc_later first in list, but enc_earlier should be episode start
        # Different facilities, 7 days gap > 5 day readmission window
        stitcher = EpisodeStitcher(readmission_window_days=5)
        episodes = stitcher.stitch([enc_later, enc_earlier])

        # They should be separate (7 days apart > 5 day window, different facilities)
        assert len(episodes) == 2
        # First episode should be the earlier one
        assert episodes[0].encounter_ids == ["enc-1"]
        assert episodes[1].encounter_ids == ["enc-2"]


# ---------------------------------------------------------------------------
# Readmission linkage (default 30 days)
# ---------------------------------------------------------------------------


class TestReadmissionLinkage:
    """Test readmission linkage rule: acute readmit within window."""

    def test_readmission_within_window_same_episode(self) -> None:
        """Acute admit within 30 days of prior acute discharge -> same episode."""
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

    def test_readmission_outside_window_separate_episodes(self) -> None:
        """Acute admit > 30 days after prior acute discharge at different facility -> separate episodes."""
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

    def test_readmission_non_acute_not_linked(self) -> None:
        """Non-acute facilities don't trigger readmission linkage."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            facility_canonical_id="FAC-001",
        )
        # Non-acute encounter at different facility, outside post-acute window
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 25, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 2, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=False,
            facility_canonical_id="FAC-SNF",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        # 20 days gap > 14 day post-acute window, different facilities, not acute
        assert len(episodes) == 2

    def test_custom_readmission_window(self) -> None:
        """Custom readmission_window_days is respected."""
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
            datetime(2024, 1, 12, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 15, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
            is_readmission=True,
            facility_canonical_id="FAC-002",
        )

        # With 5-day window, 7-day gap, different facilities -> should NOT link
        stitcher = EpisodeStitcher(readmission_window_days=5)
        episodes = stitcher.stitch([enc1, enc2])
        assert len(episodes) == 2

        # With 10-day window, 7-day gap, both acute -> should link via readmission
        stitcher = EpisodeStitcher(readmission_window_days=10)
        episodes = stitcher.stitch([enc1, enc2])
        assert len(episodes) == 1


# ---------------------------------------------------------------------------
# Post-acute linkage (default 14 days)
# ---------------------------------------------------------------------------


class TestPostAcuteLinkage:
    """Test post-acute linkage: acute discharge -> SNF/LTACH/rehab within window."""

    def test_acute_to_snf_within_window_same_episode(self) -> None:
        """Acute discharge followed by SNF admit within 14 days -> same episode."""
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
            is_acute=False,  # post-acute (SNF/LTACH/rehab)
            facility_canonical_id="FAC-SNF",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 1
        assert set(episodes[0].encounter_ids) == {"enc-1", "enc-2"}

    def test_acute_to_snf_outside_window_separate(self) -> None:
        """Acute discharge, SNF admit > 14 days later -> separate episodes."""
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
            datetime(2024, 1, 25, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 2, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=False,
            facility_canonical_id="FAC-SNF",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2


# ---------------------------------------------------------------------------
# ED bounce-back linkage (default 7 days)
# ---------------------------------------------------------------------------


class TestEdBounceback:
    """Test ED bounce-back linkage: ED visit within window of prior discharge."""

    def test_ed_bounceback_within_window_same_episode(self) -> None:
        """ED visit within 7 days of prior discharge -> same episode."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            encounter_type="inpatient",
            is_acute=True,
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 8, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 8, 18, 0, tzinfo=timezone.utc),
            encounter_type="ed_only",
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 1
        assert set(episodes[0].encounter_ids) == {"enc-1", "enc-2"}

    def test_ed_bounceback_outside_window_separate(self) -> None:
        """ED visit > 7 days after prior discharge -> separate episodes when no other rule fires."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        # Non-acute prior so readmission rule won't fire; different facility
        # so planned return won't fire. Gap > 7 days so ED bounceback won't fire.
        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            encounter_type="inpatient",
            is_acute=False,
            facility_canonical_id="FAC-001",
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 15, 18, 0, tzinfo=timezone.utc),
            encounter_type="ed_only",
            is_acute=True,
            facility_canonical_id="FAC-ED",
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2


# ---------------------------------------------------------------------------
# Planned return linkage (default 90 days)
# ---------------------------------------------------------------------------


class TestPlannedReturnLinkage:
    """Test planned return linkage: same facility within 90-day window."""

    def test_planned_return_within_window_same_episode(self) -> None:
        """Return to same acute facility within 90 days -> same episode (planned return)."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
            is_acute=True,
        )
        # Same facility, 60 days later -- planned return
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 3, 5, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 3, 8, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 1

    def test_planned_return_outside_window_separate(self) -> None:
        """Return to same facility > 90 days -> separate episodes."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
            is_acute=True,
        )
        # Same facility, 100 days later -- outside window
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 4, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 4, 18, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2

    def test_planned_return_different_facility_not_linked(self) -> None:
        """Return to different facility within 90 days -> not planned return linkage."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-001",
            is_acute=True,
        )
        # Different facility, 40 days later -- outside readmission window,
        # should NOT link via planned return (different facility)
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 2, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 2, 18, 14, 0, tzinfo=timezone.utc),
            facility_canonical_id="FAC-002",
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        assert len(episodes) == 2


# ---------------------------------------------------------------------------
# Open encounters (no discharge_ts)
# ---------------------------------------------------------------------------


class TestOpenEncounters:
    """Test handling of open encounters (no discharge_ts)."""

    def test_open_encounter_no_linkage_from_it(self) -> None:
        """Open encounter without discharge_ts can't anchor linkage to next encounter."""
        from asre.episode.episode_stitcher import EpisodeStitcher

        enc1 = _make_encounter(
            "enc-1",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            discharge_ts=None,
            status="open",
            is_acute=True,
        )
        enc2 = _make_encounter(
            "enc-2",
            "PAT-A",
            datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        episodes = stitcher.stitch([enc1, enc2])

        # Without discharge_ts, no linkage window can be computed
        assert len(episodes) == 2


# ---------------------------------------------------------------------------
# Multi-encounter chains
# ---------------------------------------------------------------------------


class TestMultiEncounterChains:
    """Test transitive episode linking across multiple encounters."""

    def test_three_encounter_chain(self) -> None:
        """A -> readmit B -> post-acute C all in same episode."""
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
        assert episodes[0].encounter_ids == ["enc-1", "enc-2", "enc-3"]
