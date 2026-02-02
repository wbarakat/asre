"""ReconcileStage - pipeline stage for cross-source reconciliation (US-063).

Processes encounters and returns reconciled encounters with timestamps
selected from the most trusted source, classification resolved by priority,
auth rules applied, and data quality flags generated.

Records stage metrics: encounters_reconciled, flags_generated (by type),
auth_without_admit_count.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.reconcile.reconciler import (
    ReconciledClassification,
    ReconciledTimestamps,
    Reconciler,
)
from asre.stitch.encounter_stitcher import StitchedEncounter

logger = logging.getLogger(__name__)


class ReconciledEncounter:
    """A StitchedEncounter enriched with reconciliation results."""

    def __init__(self, encounter: StitchedEncounter) -> None:
        self.encounter = encounter
        self.reconciled_timestamps: ReconciledTimestamps | None = None
        self.reconciled_classification: ReconciledClassification | None = None
        self.confidence_flags: list[str] = []

    # Delegate attribute access to underlying encounter
    def __getattr__(self, name: str) -> Any:
        return getattr(self.encounter, name)


class ReconcileStage(PipelineStage):
    """Pipeline stage that reconciles cross-source conflicts for encounters.

    Runs timestamp reconciliation, classification resolution, auth rules,
    timestamp mismatch flagging, and missing event pattern flagging.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("reconcile", "")
        self.encounters: list[ReconciledEncounter] = []
        self.encounters_in: list[StitchedEncounter] = []
        self.encounters_reconciled: int = 0
        self.flags_generated: dict[str, int] = {}
        self.auth_without_admit_count: int = 0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the reconcile stage.

        Args:
            batch: EventBatch (not directly used; encounters come from
                   stage.encounters_in set by the pipeline runner).
            context: Pipeline context with run_id, config, and mode.

        Returns:
            The same EventBatch (reconciled encounters stored on
            stage.encounters).
        """
        self.metrics = StageMetrics("reconcile", context.run_id)

        with self.metrics:
            encounters = list(self.encounters_in)
            self.metrics.records_in = len(encounters)

            reconciler = self._build_reconciler(context.config)
            tolerance_hours = self._get_tolerance_hours(context.config)
            now = datetime.now(tz=timezone.utc)

            reconciled: list[ReconciledEncounter] = []
            self.flags_generated = {}
            self.auth_without_admit_count = 0

            for enc in encounters:
                result = self._reconcile_encounter(
                    enc, reconciler, tolerance_hours, now
                )
                reconciled.append(result)

            self.encounters = reconciled
            self.encounters_reconciled = len(reconciled)
            self.metrics.records_out = len(reconciled)

        return batch

    def _reconcile_encounter(
        self,
        encounter: StitchedEncounter,
        reconciler: Reconciler,
        tolerance_hours: int,
        now: datetime,
    ) -> ReconciledEncounter:
        """Reconcile a single encounter and collect flags."""
        result = ReconciledEncounter(encounter)

        # Timestamp reconciliation
        result.reconciled_timestamps = reconciler.reconcile_timestamps(encounter)

        # Classification reconciliation
        result.reconciled_classification = reconciler.reconcile_classification(encounter)

        # Collect all flags
        all_flags: list[str] = []

        # Auth reconciliation
        auth_flags = reconciler.reconcile_auth(encounter)
        all_flags.extend(auth_flags)
        if "AUTH_WITHOUT_ADMIT" in auth_flags:
            self.auth_without_admit_count += 1

        # Timestamp mismatch flags
        ts_flags = reconciler.flag_timestamp_mismatches(encounter, tolerance_hours)
        all_flags.extend(ts_flags)

        # Missing event pattern flags
        all_flags.extend(reconciler.flag_missing_discharge(encounter, now))
        all_flags.extend(reconciler.flag_orphan_discharge(encounter))
        all_flags.extend(reconciler.flag_claims_only(encounter))
        all_flags.extend(reconciler.flag_adt_only(encounter, now))

        result.confidence_flags = all_flags

        # Track flag counts
        for flag in all_flags:
            self.flags_generated[flag] = self.flags_generated.get(flag, 0) + 1

        return result

    def _build_reconciler(self, config: dict[str, Any]) -> Reconciler:
        """Build a Reconciler from pipeline config."""
        recon_config: dict[str, Any] = config.get("reconciliation", {})

        kwargs: dict[str, Any] = {}
        if "timestamp_priority" in recon_config:
            kwargs["timestamp_priority"] = recon_config["timestamp_priority"]
        if "classification_priority" in recon_config:
            kwargs["classification_priority"] = recon_config["classification_priority"]

        return Reconciler(**kwargs)

    def _get_tolerance_hours(self, config: dict[str, Any]) -> int:
        """Extract timestamp tolerance hours from config."""
        recon_config: dict[str, Any] = config.get("reconciliation", {})
        tolerance: int = recon_config.get("timestamp_tolerance_hours", 24)
        return tolerance
