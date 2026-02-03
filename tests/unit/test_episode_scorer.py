"""Tests for episode-level confidence scoring (US-093)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from asre.episode.episode_scorer import EpisodeScorer
from asre.models.encounter import Encounter


def _make_encounter(
    encounter_id: str = "enc-001",
    confidence_score: float = 0.8,
    los_hours: float | None = 48.0,
) -> Encounter:
    """Helper to create a minimal encounter for scoring tests."""
    now = datetime.now(tz=timezone.utc)
    return Encounter(
        encounter_id=encounter_id,
        patient_key="PAT-001",
        encounter_type="inpatient",
        status="closed",
        admit_ts=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        facility_canonical_id="FAC-001",
        facility_name="TEST HOSPITAL",
        is_acute=True,
        source_event_ids=["evt-001"],
        source_systems=["adt_vendor_x"],
        has_adt=True,
        has_claims=False,
        has_auth=False,
        confidence_score=confidence_score,
        confidence_flags=[],
        created_at=now,
        updated_at=now,
        asre_version="0.1.0",
        los_hours=los_hours,
    )


class TestEpisodeScorer:
    """Tests for EpisodeScorer.compute_score()."""

    def test_weighted_mean_two_encounters(self) -> None:
        """Two encounters: (score 0.8, LOS 48h) and (score 0.6, LOS 24h) -> weighted mean."""
        enc_a = _make_encounter(encounter_id="enc-a", confidence_score=0.8, los_hours=48.0)
        enc_b = _make_encounter(encounter_id="enc-b", confidence_score=0.6, los_hours=24.0)

        scorer = EpisodeScorer()
        result = scorer.compute_score([enc_a, enc_b])

        # weighted mean = (0.8*48 + 0.6*24) / (48+24) = (38.4 + 14.4) / 72 = 52.8/72
        expected = (0.8 * 48.0 + 0.6 * 24.0) / (48.0 + 24.0)
        assert result == pytest.approx(expected)

    def test_ed_only_zero_los_uses_min_weight(self) -> None:
        """Encounter with zero LOS (ED-only) uses minimum weight of 1 hour."""
        enc_a = _make_encounter(encounter_id="enc-a", confidence_score=0.8, los_hours=48.0)
        enc_ed = _make_encounter(encounter_id="enc-ed", confidence_score=0.6, los_hours=0.0)

        scorer = EpisodeScorer()
        result = scorer.compute_score([enc_a, enc_ed])

        # ED encounter uses 1h weight: (0.8*48 + 0.6*1) / (48+1)
        expected = (0.8 * 48.0 + 0.6 * 1.0) / (48.0 + 1.0)
        assert result == pytest.approx(expected)

    def test_null_los_uses_min_weight(self) -> None:
        """Encounter with null LOS uses minimum weight of 1 hour."""
        enc_a = _make_encounter(encounter_id="enc-a", confidence_score=0.9, los_hours=24.0)
        enc_open = _make_encounter(encounter_id="enc-open", confidence_score=0.5, los_hours=None)

        scorer = EpisodeScorer()
        result = scorer.compute_score([enc_a, enc_open])

        # null LOS uses 1h weight: (0.9*24 + 0.5*1) / (24+1)
        expected = (0.9 * 24.0 + 0.5 * 1.0) / (24.0 + 1.0)
        assert result == pytest.approx(expected)

    def test_single_encounter(self) -> None:
        """Single encounter returns its own confidence score."""
        enc = _make_encounter(confidence_score=0.75, los_hours=36.0)

        scorer = EpisodeScorer()
        result = scorer.compute_score([enc])

        assert result == pytest.approx(0.75)

    def test_all_zero_los_encounters(self) -> None:
        """All encounters with zero LOS still produce valid weighted mean."""
        enc_a = _make_encounter(encounter_id="enc-a", confidence_score=0.8, los_hours=0.0)
        enc_b = _make_encounter(encounter_id="enc-b", confidence_score=0.4, los_hours=0.0)

        scorer = EpisodeScorer()
        result = scorer.compute_score([enc_a, enc_b])

        # Both use 1h weight: (0.8*1 + 0.4*1) / (1+1) = 0.6
        assert result == pytest.approx(0.6)

    def test_empty_encounters_returns_zero(self) -> None:
        """Empty encounter list returns 0.0."""
        scorer = EpisodeScorer()
        result = scorer.compute_score([])

        assert result == 0.0
