"""DedupStage - pipeline stage for deduplication (US-057).

Processes encounters and returns deduplicated encounters. Runs event-level
dedup first (find duplicates, resolve by source priority, mark roles), then
encounter-level dedup (merge overlapping encounters for same patient+facility).
Records stage metrics: events_before, events_after, duplicates_found,
encounters_merged.
"""

from __future__ import annotations

import logging
from typing import Any

from asre.dedup.deduplicator import Deduplicator
from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.stitch.encounter_stitcher import StitchedEncounter

logger = logging.getLogger(__name__)

# Default source priority for duplicate resolution
_DEFAULT_SOURCE_PRIORITY: dict[str, int] = {
    "adt": 100,
    "claims": 80,
    "auth": 40,
}


class DedupStage(PipelineStage):
    """Pipeline stage that deduplicates events within encounters and merges
    overlapping encounters.

    Event-level dedup runs first: identifies duplicate events within each
    encounter using match fields and time tolerance, resolves by source
    priority, and marks duplicates for audit.

    Encounter-level dedup runs second: merges overlapping encounters for
    the same patient at the same facility.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("dedup", "")
        self.encounters: list[StitchedEncounter] = []
        self.encounters_in: list[StitchedEncounter] = []
        self.events_before: int = 0
        self.events_after: int = 0
        self.duplicates_found: int = 0
        self.encounters_merged: int = 0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the dedup stage.

        Args:
            batch: EventBatch (not directly used; encounters come from
                   stage.encounters_in set by the pipeline runner).
            context: Pipeline context with run_id, config, and mode.

        Returns:
            The same EventBatch (deduplicated encounters stored on
            stage.encounters).
        """
        self.metrics = StageMetrics("dedup", context.run_id)

        with self.metrics:
            encounters = list(self.encounters_in)

            # Count events before dedup
            self.events_before = sum(len(enc.events) for enc in encounters)
            self.metrics.records_in = self.events_before

            # Build deduplicator from config
            deduplicator = self._build_deduplicator(context.config)
            source_priority = self._get_source_priority(context.config)

            # Phase 1: Event-level dedup within each encounter
            self.duplicates_found = 0
            for enc in encounters:
                dup_groups = deduplicator.find_duplicates(enc.events)
                if dup_groups:
                    kept, duplicates = deduplicator.resolve_duplicates(
                        dup_groups, source_priority
                    )
                    deduplicator.mark_roles(kept, duplicates)
                    self.duplicates_found += len(duplicates)

            # Phase 2: Encounter-level dedup (merge overlapping)
            encounters_before_merge = len(encounters)
            encounters = deduplicator.merge_overlapping_encounters(encounters)
            self.encounters_merged = encounters_before_merge - len(encounters)

            # Count non-duplicate events after dedup
            self.events_after = sum(
                1
                for enc in encounters
                for e in enc.events
                if e.role_in_encounter != "duplicate"
            )

            self.encounters = encounters
            self.metrics.records_out = len(encounters)

        return batch

    def _build_deduplicator(self, config: dict[str, Any]) -> Deduplicator:
        """Build a Deduplicator from pipeline config."""
        dedup_config: dict[str, Any] = config.get("deduplication", {})

        kwargs: dict[str, Any] = {}
        if "match_fields" in dedup_config:
            kwargs["match_fields"] = dedup_config["match_fields"]
        if "time_tolerance_minutes" in dedup_config:
            kwargs["time_tolerance_minutes"] = dedup_config["time_tolerance_minutes"]

        return Deduplicator(**kwargs)

    def _get_source_priority(self, config: dict[str, Any]) -> dict[str, int]:
        """Extract source priority from reconciliation config."""
        recon_config: dict[str, Any] = config.get("reconciliation", {})
        priority: dict[str, int] = recon_config.get(
            "timestamp_priority", _DEFAULT_SOURCE_PRIORITY
        )
        return priority
