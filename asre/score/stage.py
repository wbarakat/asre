"""ScoreStage - pipeline stage for confidence scoring (US-068).

Processes list of reconciled encounters and returns scored encounters with
confidence scores, flags, and stale encounter detection.

Records stage metrics: encounters_scored, avg_score,
score_distribution (high/medium/low/very_low counts).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.reconcile.stage import ReconciledEncounter
from asre.score.confidence_scorer import ConfidenceScorer

logger = logging.getLogger(__name__)


class ScoreStage(PipelineStage):
    """Pipeline stage that computes confidence scores for encounters.

    Runs stale encounter detection (with facility-type lookup), then
    computes confidence scores and flags for each encounter. Tracks
    scoring metrics including distribution across confidence bands.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("score", "")
        self.encounters: list[ReconciledEncounter] = []
        self.encounters_in: list[ReconciledEncounter] = []
        self.encounters_scored: int = 0
        self.avg_score: float = 0.0
        self.score_distribution: dict[str, int] = {
            "high": 0,
            "medium": 0,
            "low": 0,
            "very_low": 0,
        }

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the score stage.

        Args:
            batch: EventBatch (not directly used; encounters come from
                   stage.encounters_in set by the pipeline runner).
            context: Pipeline context with run_id, config, and mode.

        Returns:
            The same EventBatch (scored encounters stored on
            stage.encounters).
        """
        self.metrics = StageMetrics("score", context.run_id)

        with self.metrics:
            encounters = list(self.encounters_in)
            self.metrics.records_in = len(encounters)

            scorer = self._build_scorer(context.config)
            facility_type_map = self._get_facility_type_map(context.config)
            now = datetime.now(tz=timezone.utc)

            scored: list[ReconciledEncounter] = []
            total_score = 0.0
            distribution: dict[str, int] = {
                "high": 0,
                "medium": 0,
                "low": 0,
                "very_low": 0,
            }

            for enc in encounters:
                self._score_encounter(enc, scorer, facility_type_map, now)
                scored.append(enc)
                score = enc.confidence_score
                total_score += score
                band = self._classify_score(score)
                distribution[band] += 1

            self.encounters = scored
            self.encounters_scored = len(scored)
            self.avg_score = total_score / len(scored) if scored else 0.0
            self.score_distribution = distribution
            self.metrics.records_out = len(scored)

        return batch

    def _score_encounter(
        self,
        encounter: ReconciledEncounter,
        scorer: ConfidenceScorer,
        facility_type_map: dict[str, str],
        now: datetime,
    ) -> None:
        """Score a single encounter: detect stale, compute score, build flags."""
        # Look up facility type for stale detection
        facility_type: str | None = None
        fac_id = encounter.facility_canonical_id
        if fac_id is not None:
            facility_type = facility_type_map.get(fac_id)

        # Detect stale encounters and add flag before scoring
        stale_flags = scorer.detect_stale_encounter(
            encounter, now=now, facility_type=facility_type
        )
        for flag in stale_flags:
            if flag not in encounter.confidence_flags:
                encounter.confidence_flags.append(flag)

        # Compute confidence score
        score = scorer.compute_score(encounter)
        encounter.confidence_score = score  # type: ignore[attr-defined]

        # Build full confidence flags (signals + penalties)
        encounter.confidence_flags = scorer.build_confidence_flags(encounter)

    @staticmethod
    def _classify_score(score: float) -> str:
        """Classify a score into a confidence band.

        High: 0.85-1.0, Medium: 0.60-0.84, Low: 0.30-0.59, Very Low: 0.00-0.29
        """
        if score >= 0.85:
            return "high"
        if score >= 0.60:
            return "medium"
        if score >= 0.30:
            return "low"
        return "very_low"

    def _build_scorer(self, config: dict[str, Any]) -> ConfidenceScorer:
        """Build a ConfidenceScorer from pipeline config."""
        score_config: dict[str, Any] = config.get("confidence_scoring", {})

        kwargs: dict[str, Any] = {}
        if "signal_weights" in score_config:
            kwargs["signal_weights"] = score_config["signal_weights"]
        if "penalty_weights" in score_config:
            kwargs["penalty_weights"] = score_config["penalty_weights"]
        if "stale_thresholds" in score_config:
            kwargs["stale_thresholds"] = score_config["stale_thresholds"]

        return ConfidenceScorer(**kwargs)

    def _get_facility_type_map(self, config: dict[str, Any]) -> dict[str, str]:
        """Extract facility_id -> facility_type mapping from config.

        The pipeline runner should populate this from the FacilityRegistry
        before invoking the score stage.
        """
        result: dict[str, str] = config.get("facility_registry_map", {})
        return result
