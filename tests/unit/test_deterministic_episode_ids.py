"""Tests for deterministic episode ID generation — US-090.

Verifies that episode IDs are:
1. Deterministically derived from the first encounter in the episode
2. Stable across repeated runs with the same encounters
3. Different for different first encounters
"""

from __future__ import annotations

from datetime import datetime, timezone

from asre.episode.episode_stitcher import EpisodeStitcher, generate_episode_id
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
    )


class TestGenerateEpisodeId:
    """Test the generate_episode_id function directly."""

    def test_same_encounter_produces_same_id(self) -> None:
        """Same first encounter always produces the same episode_id."""
        id1 = generate_episode_id("enc-abc-123")
        id2 = generate_episode_id("enc-abc-123")
        assert id1 == id2

    def test_different_encounter_produces_different_id(self) -> None:
        """Different first encounter_ids produce different episode_ids."""
        id1 = generate_episode_id("enc-abc-123")
        id2 = generate_episode_id("enc-def-456")
        assert id1 != id2

    def test_returns_hex_string(self) -> None:
        """Episode ID is a hex string (URL-safe)."""
        ep_id = generate_episode_id("enc-abc-123")
        assert isinstance(ep_id, str)
        assert len(ep_id) > 0
        # Should be valid hex
        int(ep_id, 16)

    def test_has_episode_prefix_in_hash_input(self) -> None:
        """Episode ID differs from encounter ID even for same input string.

        The hash includes a domain separator so episode IDs don't collide
        with encounter IDs.
        """
        import hashlib

        # Raw encounter hash (what encounter IDs do)
        raw_enc = hashlib.sha256(b"enc-abc-123").hexdigest()
        ep_id = generate_episode_id("enc-abc-123")
        assert ep_id != raw_enc


class TestDeterministicEpisodeIdsInStitcher:
    """Test that EpisodeStitcher produces stable episode IDs via _EpisodeGroup."""

    def test_same_encounters_produce_same_episode_id_on_repeated_runs(self) -> None:
        """Running stitch twice with the same encounters produces the same episode_id."""
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
        )
        stitcher = EpisodeStitcher()

        groups_run1 = stitcher.stitch([enc1, enc2])
        groups_run2 = stitcher.stitch([enc1, enc2])

        assert len(groups_run1) == 1
        assert len(groups_run2) == 1
        assert groups_run1[0].episode_id == groups_run2[0].episode_id

    def test_different_first_encounters_produce_different_episode_ids(self) -> None:
        """Episodes with different first encounters have different IDs."""
        enc_a = _make_encounter(
            "enc-A",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
        )
        enc_b = _make_encounter(
            "enc-B",
            "PAT-B",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
        )
        stitcher = EpisodeStitcher()

        groups = stitcher.stitch([enc_a, enc_b])
        assert len(groups) == 2
        assert groups[0].episode_id != groups[1].episode_id

    def test_episode_id_derived_from_first_encounter(self) -> None:
        """Episode ID is deterministically derived from the first encounter_id in the group."""
        enc1 = _make_encounter(
            "enc-first",
            "PAT-A",
            datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        enc2 = _make_encounter(
            "enc-second",
            "PAT-A",
            datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            is_acute=True,
        )
        stitcher = EpisodeStitcher()
        groups = stitcher.stitch([enc1, enc2])

        assert len(groups) == 1
        expected_id = generate_episode_id("enc-first")
        assert groups[0].episode_id == expected_id

    def test_multi_patient_episode_ids_unique(self) -> None:
        """Each patient's episode gets a unique ID."""
        encs = [
            _make_encounter(
                f"enc-{p}-1",
                f"PAT-{p}",
                datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
                datetime(2024, 1, 5, 14, 0, tzinfo=timezone.utc),
            )
            for p in ["A", "B", "C"]
        ]
        stitcher = EpisodeStitcher()
        groups = stitcher.stitch(encs)

        assert len(groups) == 3
        ids = [g.episode_id for g in groups]
        assert len(set(ids)) == 3  # all unique
