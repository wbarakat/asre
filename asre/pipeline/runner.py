"""Pipeline stage interface, context, and orchestrator for ASRE pipeline."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from asre.models.batch import EventBatch

logger = logging.getLogger(__name__)


@dataclass
class PipelineContext:
    """Context passed to each pipeline stage during execution.

    Holds run-level state: run_id, config, mode, and optional metrics collector.
    """

    run_id: str
    config: dict[str, Any]
    mode: str
    metrics_collector: Any = field(default=None)


class PipelineStage(ABC):
    """Abstract base class for all ASRE pipeline stages.

    Each stage processes an EventBatch and returns a (possibly modified) EventBatch.
    """

    @abstractmethod
    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute this pipeline stage.

        Args:
            batch: The current event batch to process.
            context: Pipeline-level context (run_id, config, mode, metrics).

        Returns:
            The processed EventBatch.
        """


class _NoOpStage(PipelineStage):
    """Placeholder stage for not-yet-implemented pipeline stages."""

    def __init__(self, name: str) -> None:
        self._name = name
        from asre.observability.metrics import StageMetrics

        self.metrics: Any = StageMetrics(name, "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        logger.info("Stage %s: no-op (not yet implemented)", self._name)
        return batch


# Stage ordering for the full pipeline
_STAGE_ORDER: list[str] = [
    "ingest",
    "canonicalize",
    "facility_normalize",
    "stitch",
    "dedup",
    "reconcile",
    "score",
    "materialize",
    "quality_check",
]


class PipelineRunner:
    """Orchestrates the ASRE pipeline stages in sequence.

    Sequences stages: Ingest -> Canonicalize -> FacilityNormalize -> Stitch
    -> Dedup -> Reconcile -> Score -> Materialize -> QualityCheck.

    Handles data handoff between stages and collects per-stage metrics.
    """

    def __init__(self, config: dict[str, Any], mode: str) -> None:
        self._config = config
        self.mode = mode
        self.run_id = self._generate_run_id()
        self._stages: dict[str, PipelineStage] = self._build_stages()
        self.stage_metrics: list[dict[str, Any]] = []

    @staticmethod
    def _generate_run_id() -> str:
        now = datetime.now(tz=timezone.utc)
        return f"run_{now.strftime('%Y%m%d_%H%M%S')}"

    def _build_stages(self) -> dict[str, PipelineStage]:
        """Build the default stage instances.

        Uses actual stage implementations where available, and no-op
        placeholders for stages not yet implemented.
        """
        stages: dict[str, PipelineStage] = OrderedDict()

        # Ingest
        from asre.ingest.stage import IngestStage

        stages["ingest"] = IngestStage()

        # Canonicalize
        from asre.canonicalize.stage import CanonicalizeStage

        stages["canonicalize"] = CanonicalizeStage()

        # Facility normalize - requires config-dependent construction
        stages["facility_normalize"] = self._build_facility_stage()

        # Stitch
        from asre.stitch.stage import StitchStage

        stages["stitch"] = StitchStage()

        # Dedup
        from asre.dedup.stage import DedupStage

        stages["dedup"] = DedupStage()

        # Reconcile
        from asre.reconcile.stage import ReconcileStage

        stages["reconcile"] = ReconcileStage()

        # Score
        from asre.score.stage import ScoreStage

        stages["score"] = ScoreStage()

        # Materialize
        from asre.materialize.stage import MaterializeStage

        stages["materialize"] = MaterializeStage()

        # Quality Check (placeholder)
        stages["quality_check"] = _NoOpStage("quality_check")

        return stages

    def _build_facility_stage(self) -> PipelineStage:
        """Build FacilityNormalizationStage from config."""
        from asre.config.facility_alias_schema import FacilityAliasConfig
        from asre.facility.normalizer import FacilityNormalizer
        from asre.facility.registry import FacilityRegistry
        from asre.facility.stage import FacilityNormalizationStage

        normalizer = FacilityNormalizer()
        alias_config = self._config.get("facility_aliases")
        if alias_config is None or not isinstance(alias_config, FacilityAliasConfig):
            alias_config = FacilityAliasConfig(facilities=[])

        facility_normalization_cfg = self._config.get("facility_normalization", {})
        fuzzy_threshold: float = 0.85
        if hasattr(facility_normalization_cfg, "fuzzy_threshold"):
            fuzzy_threshold = facility_normalization_cfg.fuzzy_threshold
        elif isinstance(facility_normalization_cfg, dict):
            fuzzy_threshold = facility_normalization_cfg.get(
                "fuzzy_threshold", 0.85
            )

        registry = FacilityRegistry(alias_config, normalizer)

        return FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
            fuzzy_threshold=fuzzy_threshold,
        )

    def _get_checkpoint_manager(self) -> Any:
        """Get a CheckpointManager if an adapter is available in config."""
        adapter = self._config.get("adapter")
        if adapter is None:
            return None
        from asre.pipeline.checkpoint import CheckpointManager

        return CheckpointManager(adapter)

    def run(self, resume_run_id: str | None = None) -> dict[str, Any]:
        """Execute the full pipeline.

        Args:
            resume_run_id: If provided, resume from the last completed stage
                of the given run. The checkpoint must exist and be resumable.

        Returns:
            Summary dict with run_id, mode, and stage metrics.
        """
        checkpoint_mgr = self._get_checkpoint_manager()
        skip_through_index = -1

        if resume_run_id is not None:
            if checkpoint_mgr is None:
                raise ValueError(
                    f"Cannot resume run '{resume_run_id}': no adapter configured"
                )
            cp = checkpoint_mgr.load_checkpoint(resume_run_id)
            if cp is None:
                raise ValueError(
                    f"Checkpoint for run '{resume_run_id}' not found"
                )
            if cp.get("status") == "completed":
                raise ValueError(
                    f"Run '{resume_run_id}' already completed"
                )
            skip_through_index = cp["stage_index"]
            self.run_id = resume_run_id

        batch = EventBatch(batch_id=self.run_id, events=[])
        context = PipelineContext(
            run_id=self.run_id,
            config=dict(self._config),
            mode=self.mode,
        )

        # Set up audit logger if adapter is available
        adapter = self._config.get("adapter")
        if adapter is not None:
            from asre.pipeline.audit import AuditLogger

            audit_logger = AuditLogger(adapter=adapter, run_id=self.run_id)
            audit_logger.ensure_table()
            context.config["audit_logger"] = audit_logger

        self.stage_metrics = []

        for idx, stage_name in enumerate(_STAGE_ORDER):
            # Skip stages that were already completed in a prior run
            if idx <= skip_through_index:
                logger.info(
                    "Skipping stage: %s (already completed, run_id=%s)",
                    stage_name,
                    self.run_id,
                )
                continue

            stage = self._stages[stage_name]

            logger.info("Starting stage: %s (run_id=%s)", stage_name, self.run_id)
            try:
                batch = stage.run(batch, context)
            except Exception:
                if checkpoint_mgr is not None:
                    # Record the failure — last_completed_stage is the
                    # previous stage (idx-1), but we store the failing
                    # stage name so resume knows where to retry.
                    prev_stage = _STAGE_ORDER[idx - 1] if idx > 0 else stage_name
                    checkpoint_mgr.mark_failed(
                        run_id=self.run_id,
                        stage_name=prev_stage,
                        stage_index=idx - 1 if idx > 0 else 0,
                        error=f"Stage {stage_name} failed",
                    )
                raise
            logger.info("Completed stage: %s", stage_name)

            # Data handoff between stages
            self._handoff(stage_name, stage, context)

            # Collect metrics
            if hasattr(stage, "metrics") and hasattr(stage.metrics, "to_dict"):
                self.stage_metrics.append(stage.metrics.to_dict())

            # Save checkpoint after successful stage
            if checkpoint_mgr is not None:
                checkpoint_mgr.save_checkpoint(
                    run_id=self.run_id,
                    stage_name=stage_name,
                    stage_index=idx,
                )

        # Mark run as completed
        if checkpoint_mgr is not None:
            checkpoint_mgr.mark_completed(self.run_id)

        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "stages_completed": len(self.stage_metrics),
        }

    def _handoff(
        self,
        stage_name: str,
        stage: PipelineStage,
        context: PipelineContext,
    ) -> None:
        """Transfer data between stages after each stage completes."""
        if stage_name == "ingest":
            # Pass raw records to canonicalize via config
            if hasattr(stage, "raw_records"):
                context.config["raw_records"] = stage.raw_records

        elif stage_name == "facility_normalize":
            # Build facility_registry_map for ScoreStage
            if hasattr(stage, "_registry"):
                registry_map: dict[str, str] = {}
                for record in stage._registry.get_all_facilities():
                    if record.facility_type:
                        registry_map[record.canonical_id] = record.facility_type
                context.config["facility_registry_map"] = registry_map

        elif stage_name == "stitch":
            # Pass encounters to dedup
            dedup = self._stages.get("dedup")
            if hasattr(stage, "encounters") and hasattr(dedup, "encounters_in"):
                dedup.encounters_in = stage.encounters  # type: ignore[union-attr]

        elif stage_name == "dedup":
            # Pass encounters to reconcile
            reconcile = self._stages.get("reconcile")
            if hasattr(stage, "encounters") and hasattr(reconcile, "encounters_in"):
                reconcile.encounters_in = stage.encounters  # type: ignore[union-attr]

        elif stage_name == "reconcile":
            # Pass encounters to score
            score = self._stages.get("score")
            if hasattr(stage, "encounters") and hasattr(score, "encounters_in"):
                score.encounters_in = stage.encounters  # type: ignore[union-attr]

        elif stage_name == "score":
            # Pass scored encounters to materialize
            materialize = self._stages.get("materialize")
            if hasattr(stage, "encounters") and hasattr(materialize, "encounters_in"):
                materialize.encounters_in = stage.encounters  # type: ignore[union-attr]
