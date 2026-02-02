"""FacilityNormalizationStage - pipeline stage for facility name resolution.

Processes each canonical event: normalizes facility_raw, matches against
known facilities (exact alias, NPI, CCN, fuzzy), and sets facility_canonical_id.
Updates facility registry with any new facilities created during resolution.
"""

from __future__ import annotations

import logging
from typing import Any

from asre.config.facility_alias_schema import FacilityAliasConfig
from asre.facility.matcher import FacilityMatcher, MatchResult
from asre.facility.normalizer import FacilityNormalizer
from asre.facility.registry import FacilityRegistry
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class FacilityNormalizationStage(PipelineStage):
    """Pipeline stage that resolves facility names to canonical IDs.

    For each canonical event, normalizes facility_raw, matches against
    the facility registry, and sets facility_canonical_id. Unresolved
    facilities are created as new entries flagged for review.
    """

    def __init__(
        self,
        normalizer: FacilityNormalizer,
        alias_config: FacilityAliasConfig,
        registry: FacilityRegistry,
        fuzzy_threshold: float = 0.85,
    ) -> None:
        self._normalizer = normalizer
        self._alias_config = alias_config
        self._registry = registry
        self._matcher = FacilityMatcher(
            alias_config=alias_config,
            normalizer=normalizer,
            fuzzy_threshold=fuzzy_threshold,
        )
        self.metrics: StageMetrics = StageMetrics("facility_normalize", "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the facility normalization stage.

        Args:
            batch: EventBatch containing canonical events with facility_raw set.
            context: Pipeline context with run_id and config.

        Returns:
            The same EventBatch with facility_canonical_id populated on events.
        """
        self.metrics = StageMetrics("facility_normalize", context.run_id)

        with self.metrics:
            self.metrics.records_in = len(batch.events)

            for event in batch.events:
                self._resolve_facility(event)

            self.metrics.records_out = len(batch.events)

        return batch

    def _resolve_facility(self, event: CanonicalEvent) -> None:
        """Resolve a single event's facility_raw to facility_canonical_id.

        Uses FacilityMatcher.resolve_or_create() which cascades through:
        exact alias -> NPI -> CCN -> fuzzy -> create new.

        New facilities are added to the registry.
        """
        facility_raw = event.facility_raw
        if not facility_raw or not facility_raw.strip():
            return

        # Extract NPI/CCN from raw payload if available
        npi: str | None = None
        ccn: str | None = None
        if event._raw_payload:
            npi = event._raw_payload.get("npi")
            ccn = event._raw_payload.get("ccn")

        result = self._matcher.resolve_or_create(
            facility_name=facility_raw,
            npi=npi,
            ccn=ccn,
        )

        if result is None:
            return

        event.facility_canonical_id = result.canonical_id

        # If a new facility was created, register it in the registry
        if result.match_type == "new":
            normalized_name = self._normalizer.normalize(facility_raw)
            self._registry.add_facility(
                canonical_id=result.canonical_id,
                canonical_name=facility_raw,
                aliases=[normalized_name] if normalized_name else [],
                flags=list(result.flags),
            )
            logger.info(
                "New facility created: %s (%s) - flagged %s",
                result.canonical_id,
                facility_raw,
                result.flags,
            )
        else:
            logger.debug(
                "Facility resolved: %s -> %s (match_type=%s, score=%.2f)",
                facility_raw,
                result.canonical_id,
                result.match_type,
                result.score,
            )
