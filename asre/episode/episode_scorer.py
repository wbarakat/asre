"""EpisodeScorer — episode-level confidence as LOS-weighted mean of encounters (US-093).

Per SPEC section 9.4:
  episode_confidence = sum(encounter_confidence_i * los_hours_i) / sum(los_hours_i)

Encounters with zero or null LOS (e.g., ED-only) use a minimum weight of 1 hour.
"""

from __future__ import annotations

from asre.models.encounter import Encounter

_MIN_WEIGHT_HOURS = 1.0


class EpisodeScorer:
    """Computes episode-level confidence as a LOS-weighted mean of encounter scores."""

    def compute_score(self, encounters: list[Encounter]) -> float:
        """Compute weighted mean confidence for an episode's encounters.

        Returns 0.0 for empty encounter lists.
        """
        if not encounters:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        for enc in encounters:
            weight = enc.los_hours if enc.los_hours and enc.los_hours > 0 else _MIN_WEIGHT_HOURS
            weighted_sum += enc.confidence_score * weight
            total_weight += weight

        return weighted_sum / total_weight
