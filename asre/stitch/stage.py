"""StitchStage - pipeline stage for encounter stitching (US-052).

Processes EventBatch of canonical events and produces encounters using
EncounterStitcher. Builds encounter metadata for each stitched encounter.
Records stage metrics: events_in, encounters_out, transfers_detected,
cancellations_processed.
"""

from __future__ import annotations

import logging
from typing import Any

from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.stitch.encounter_stitcher import EncounterStitcher, StitchedEncounter
from asre.stitch.metadata import EncounterMetadata, build_encounter_metadata

logger = logging.getLogger(__name__)

# Cancellation event types tracked for metrics
_CANCELLATION_EVENT_TYPES = {"CANCEL_ADMIT", "CANCEL_DISCHARGE"}


class StitchStage(PipelineStage):
    """Pipeline stage that stitches canonical events into encounters.

    Uses EncounterStitcher to group events by patient, facility, and time window.
    Builds metadata for each encounter and tracks stage metrics.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("stitch", "")
        self.encounters: list[StitchedEncounter] = []
        self.encounter_metadata: list[EncounterMetadata] = []
        self.transfers_detected: int = 0
        self.cancellations_processed: int = 0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the stitch stage.

        Args:
            batch: EventBatch containing canonical events to stitch.
            context: Pipeline context with run_id, config, and mode.

        Returns:
            The same EventBatch (encounters stored on stage.encounters).
        """
        self.metrics = StageMetrics("stitch", context.run_id)

        with self.metrics:
            self.metrics.records_in = len(batch.events)

            # Build stitcher from config
            stitcher = self._build_stitcher(context.config)

            # Stitch events into encounters
            self.encounters = stitcher.stitch(batch.events)

            # Build metadata for each encounter
            self.encounter_metadata = [
                build_encounter_metadata(enc) for enc in self.encounters
            ]

            # Count transfers
            self.transfers_detected = self._count_transfers(self.encounters)

            # Count cancellation events
            self.cancellations_processed = self._count_cancellations(batch.events)

            self.metrics.records_out = len(self.encounters)

        return batch

    def _build_stitcher(self, config: dict[str, Any]) -> EncounterStitcher:
        """Build an EncounterStitcher from pipeline config.

        Reads encounter_stitching config section for time_window_hours,
        facility_must_match, same_timestamp_tiebreaker, patient_class_transitions.
        Uses defaults when config keys are missing.
        """
        stitch_config: dict[str, Any] = config.get("encounter_stitching", {})

        kwargs: dict[str, Any] = {}
        if "time_window_hours" in stitch_config:
            kwargs["time_window_hours"] = stitch_config["time_window_hours"]
        if "facility_must_match" in stitch_config:
            kwargs["facility_must_match"] = stitch_config["facility_must_match"]
        if "same_timestamp_tiebreaker" in stitch_config:
            kwargs["same_timestamp_tiebreaker"] = stitch_config[
                "same_timestamp_tiebreaker"
            ]
        if "patient_class_transitions" in stitch_config:
            kwargs["patient_class_transitions"] = stitch_config[
                "patient_class_transitions"
            ]

        return EncounterStitcher(**kwargs)

    def _count_transfers(self, encounters: list[StitchedEncounter]) -> int:
        """Count the number of transfer chains detected.

        A transfer chain links 2+ encounters. We count unique chains,
        not individual encounters in chains.
        """
        seen_chains: set[tuple[int, ...]] = set()
        for enc in encounters:
            if enc.transfer_chain:
                chain_key = tuple(enc.transfer_chain)
                seen_chains.add(chain_key)
        return len(seen_chains)

    def _count_cancellations(self, events: list[Any]) -> int:
        """Count cancellation events (CANCEL_ADMIT, CANCEL_DISCHARGE)."""
        count = 0
        for event in events:
            if hasattr(event, "event_type") and event.event_type in _CANCELLATION_EVENT_TYPES:
                count += 1
        return count
