"""Pipeline stage interface, context, and orchestrator for ASRE pipeline."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
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
    "episode_stitch",
    "episode_materialize",
    "episode_quality",
]

# Tables to clear before a full refresh run
_FULL_REFRESH_TABLES: list[str] = [
    "admission_events_unified",
    "asre_encounters_detail",
    "asre_episodes",
    "asre_quality_metrics",
    "asre_run_metrics",
    "asre_audit_log",
    "asre_canonical_events",
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

        # Quality Check
        from asre.quality.stage import QualityCheckStage

        stages["quality_check"] = QualityCheckStage()

        # Episode Stitch
        from asre.episode.stage import EpisodeStitchStage

        stages["episode_stitch"] = EpisodeStitchStage()

        # Episode Materialize
        from asre.episode.stage import EpisodeMaterializeStage

        stages["episode_materialize"] = EpisodeMaterializeStage()

        # Episode Quality
        from asre.episode.stage import EpisodeQualityStage

        stages["episode_quality"] = EpisodeQualityStage()

        return stages

    # Default bundled SQLite registry path (inside package)
    _DEFAULT_SQLITE_REGISTRY = (
        Path(__file__).parent.parent / "data" / "facility_registry.db"
    )

    def _build_facility_stage(self) -> PipelineStage:
        """Build FacilityNormalizationStage from config."""
        from asre.config.facility_alias_schema import FacilityAliasConfig
        from asre.facility.normalizer import FacilityNormalizer
        from asre.facility.registry import FacilityRegistry
        from asre.facility.stage import FacilityNormalizationStage
        from asre.facility.registry_loader import load_facility_registry_csv
        from pathlib import Path

        alias_config = self._config.get("facility_aliases")
        if alias_config is None or not isinstance(alias_config, FacilityAliasConfig):
            alias_config = FacilityAliasConfig(facilities=[])

        facility_normalization_cfg = self._config.get("facility_normalization", {})
        fuzzy_threshold: float = 0.85
        abbreviations: dict[str, str] | None = None
        registry_path: str | None = None
        sqlite_registry_path: str | None = None
        use_npi_registry = True
        use_ccn_registry = True
        if hasattr(facility_normalization_cfg, "fuzzy_threshold"):
            fuzzy_threshold = facility_normalization_cfg.fuzzy_threshold
            abbreviations = facility_normalization_cfg.abbreviations
            registry_path = getattr(facility_normalization_cfg, "registry_path", None)
            sqlite_registry_path = getattr(facility_normalization_cfg, "sqlite_registry_path", None)
            use_npi_registry = getattr(facility_normalization_cfg, "use_npi_registry", True)
            use_ccn_registry = getattr(facility_normalization_cfg, "use_ccn_registry", True)
        elif isinstance(facility_normalization_cfg, dict):
            fuzzy_threshold = facility_normalization_cfg.get(
                "fuzzy_threshold", 0.85
            )
            abbreviations = facility_normalization_cfg.get("abbreviations")
            registry_path = facility_normalization_cfg.get("registry_path")
            sqlite_registry_path = facility_normalization_cfg.get("sqlite_registry_path")
            use_npi_registry = facility_normalization_cfg.get("use_npi_registry", True)
            use_ccn_registry = facility_normalization_cfg.get("use_ccn_registry", True)

        normalizer = FacilityNormalizer(abbreviations=abbreviations)

        # Load NPI/CCN registry entries if provided
        registry_aliases = None
        if registry_path:
            try:
                registry_aliases = load_facility_registry_csv(
                    Path(registry_path),
                    use_npi_registry=use_npi_registry,
                    use_ccn_registry=use_ccn_registry,
                )
            except FileNotFoundError:
                logger.warning("Facility registry path not found: %s", registry_path)

        if registry_aliases is not None and registry_aliases.facilities:
            combined = list(registry_aliases.facilities)
            combined.extend(alias_config.facilities)
            alias_config = FacilityAliasConfig(facilities=combined)

        registry = FacilityRegistry(alias_config, normalizer)

        # Load SQLite registry for NPI/CCN fallback lookup
        sqlite_lookup = None
        if sqlite_registry_path is None:
            # Auto-detect bundled default
            if self._DEFAULT_SQLITE_REGISTRY.exists():
                sqlite_registry_path = str(self._DEFAULT_SQLITE_REGISTRY)
        if sqlite_registry_path and Path(sqlite_registry_path).exists():
            from asre.facility.sqlite_registry import SQLiteRegistryLookup
            sqlite_lookup = SQLiteRegistryLookup(sqlite_registry_path)
            logger.info("Loaded SQLite facility registry: %s", sqlite_registry_path)

        return FacilityNormalizationStage(
            normalizer=normalizer,
            alias_config=alias_config,
            registry=registry,
            fuzzy_threshold=fuzzy_threshold,
            sqlite_lookup=sqlite_lookup,
        )

    def _get_checkpoint_manager(self) -> Any:
        """Get a CheckpointManager if an adapter is available in config."""
        adapter = self._config.get("adapter")
        if adapter is None:
            return None
        from asre.pipeline.checkpoint import CheckpointManager

        mgr = CheckpointManager(adapter)
        mgr.ensure_table()
        return mgr

    def _get_health_state(self) -> Any | None:
        """Return configured health state tracker if present."""
        state = self._config.get("health_state")
        if state is None:
            return None
        if not hasattr(state, "mark_failed") or not hasattr(state, "mark_ok"):
            return None
        return state

    def run(self, resume_run_id: str | None = None) -> dict[str, Any]:
        """Execute the full pipeline.

        Args:
            resume_run_id: If provided, resume from the last completed stage
                of the given run. The checkpoint must exist and be resumable.

        Returns:
            Summary dict with run_id, mode, and stage metrics.
        """
        health_state = self._get_health_state()
        if health_state is not None:
            health_state.mark_ok()

        try:
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
                self.run_id = resume_run_id
                stage_index = cp.get("stage_index", -1)
                if isinstance(stage_index, str):
                    stage_index = int(stage_index)
                if stage_index >= 7:
                    skip_through_index = stage_index
                    logger.info(
                        "Resuming run %s: skipping through stage index %d, "
                        "rehydrating from materialized data",
                        resume_run_id,
                        stage_index,
                    )
                else:
                    skip_through_index = -1
                    logger.warning(
                        "Resuming run %s by replaying all stages "
                        "(checkpoint at stage index %d < 7)",
                        resume_run_id,
                        stage_index,
                    )

            batch = EventBatch(batch_id=self.run_id, events=[])
            context = PipelineContext(
                run_id=self.run_id,
                config=dict(self._config),
                mode=self.mode,
            )

            # Set up audit logger and run metrics writer if adapter is available
            adapter = self._config.get("adapter")
            metrics_writer = None
            if adapter is not None:
                from asre.pipeline.audit import AuditLogger

                audit_logger = AuditLogger(adapter=adapter, run_id=self.run_id)
                audit_logger.ensure_table()
                context.config["audit_logger"] = audit_logger

                from asre.observability.run_metrics_writer import RunMetricsWriter

                metrics_writer = RunMetricsWriter(adapter)
                metrics_writer.ensure_table()

            self.stage_metrics = []

            stage_names = list(self._stages.keys())

            # Full refresh cleanup before processing stages
            if (
                self.mode == "full"
                and adapter is not None
                and not context.config.get("dry_run", False)
            ):
                self._full_refresh_cleanup(adapter)

            # Rehydrate data if skipping post-materialize stages
            if skip_through_index >= 7:
                self._rehydrate_post_materialize(context)

            for idx, stage_name in enumerate(stage_names):
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
                except Exception as exc:
                    if health_state is not None:
                        health_state.mark_failed(
                            f"Stage {stage_name} failed: {exc}"
                        )
                    if checkpoint_mgr is not None:
                        # Rollback any aborted transaction so checkpoint write succeeds
                        adapter = self._config.get("adapter")
                        if adapter is not None and hasattr(adapter, "_connection"):
                            try:
                                adapter._connection.rollback()
                            except Exception as rollback_exc:
                                logger.debug(
                                    "Checkpoint rollback after stage failure failed: %s",
                                    rollback_exc,
                                )
                        # Record the failure -- last_completed_stage is the
                        # previous stage (idx-1), but we store the failing
                        # stage name so resume knows where to retry.
                        prev_stage = stage_names[idx - 1] if idx > 0 else stage_name
                        try:
                            checkpoint_mgr.mark_failed(
                                run_id=self.run_id,
                                stage_name=prev_stage,
                                stage_index=idx - 1 if idx > 0 else 0,
                                error=f"Stage {stage_name} failed: {exc}",
                            )
                        except Exception:
                            logger.warning(
                                "Failed to save checkpoint for failed stage %s",
                                stage_name,
                            )
                    raise
                logger.info("Completed stage: %s", stage_name)

                # Data handoff between stages
                self._handoff(stage_name, stage, context)

                # Collect metrics
                if hasattr(stage, "metrics") and hasattr(stage.metrics, "to_dict"):
                    self.stage_metrics.append(stage.metrics.to_dict())

                # Check error tolerance after each stage
                self._check_error_tolerance()

                # Save checkpoint after successful stage
                if checkpoint_mgr is not None:
                    checkpoint_mgr.save_checkpoint(
                        run_id=self.run_id,
                        stage_name=stage_name,
                        stage_index=idx,
                    )

            # Persist run metrics to asre_run_metrics table
            if metrics_writer is not None and self.stage_metrics:
                metrics_writer.write_metrics(self.stage_metrics)

            # Mark run as completed
            if checkpoint_mgr is not None:
                last_stage = stage_names[-1] if stage_names else ""
                last_index = len(stage_names) - 1 if stage_names else 0
                checkpoint_mgr.mark_completed(
                    self.run_id,
                    stage_name=last_stage,
                    stage_index=last_index,
                )

            return {
                "run_id": self.run_id,
                "mode": self.mode,
                "stages_completed": len(self.stage_metrics),
            }
        except Exception as exc:
            if health_state is not None and getattr(health_state, "is_healthy", None):
                if health_state.is_healthy():
                    health_state.mark_failed(str(exc))
            raise

    def _get_fail_threshold(self) -> float:
        """Get the failed_event_rate_fail threshold from config."""
        alerting = self._config.get("alerting", {})
        if hasattr(alerting, "thresholds"):
            # Pydantic model
            thresholds = alerting.thresholds
        elif isinstance(alerting, dict):
            thresholds = alerting.get("thresholds", {})
        else:
            thresholds = {}

        if isinstance(thresholds, dict):
            return float(thresholds.get("failed_event_rate_fail", 0.05))
        return 0.05

    def _check_error_tolerance(self) -> None:
        """Check cumulative failed event rate across all completed stages.

        Raises FailedEventRateExceededError if rate >= threshold.
        """
        from asre.pipeline.error_tolerance import ErrorToleranceChecker

        total_in = 0
        total_errors = 0
        for m in self.stage_metrics:
            total_in += m.get("records_in", 0)
            total_errors += m.get("errors", 0)

        if total_in == 0:
            return

        threshold = self._get_fail_threshold()
        checker = ErrorToleranceChecker(fail_threshold=threshold)
        checker.check(failed=total_errors, total=total_in)

    @staticmethod
    def _full_refresh_cleanup(adapter: Any) -> None:
        """Clear derived tables for a full refresh run."""
        for table in _FULL_REFRESH_TABLES:
            try:
                adapter.execute_ddl(f"DELETE FROM {table} WHERE 1=1")  # nosec B608
            except Exception:
                logger.warning(
                    "Full refresh cleanup skipped for missing table: %s", table
                )

    def _rehydrate_post_materialize(self, context: PipelineContext) -> None:
        """Rehydrate encounter data from materialized tables for resume.

        Reads encounters from admission_events_unified and prior stage metrics
        from asre_run_metrics, then populates the context so post-materialize
        stages (quality_check, episode_stitch, etc.) have their inputs.
        """
        adapter = context.config.get("adapter")
        if adapter is None:
            logger.warning("No adapter available for rehydration")
            return

        # Read encounters from admission_events_unified
        try:
            rows = adapter.read_source(
                "admission_events_unified",
                "SELECT * FROM admission_events_unified WHERE asre_version IS NOT NULL",
            )
        except Exception:
            logger.warning("Could not read admission_events_unified for rehydration")
            rows = []

        # Convert to lightweight encounter-like objects
        from types import SimpleNamespace

        scored_encounters = []
        for row in rows:
            enc = SimpleNamespace(
                encounter_id=row.get("encounter_id"),
                patient_key=row.get("patient_key"),
                encounter_type=row.get("encounter_type"),
                status=row.get("status"),
                admit_ts=row.get("admit_ts"),
                discharge_ts=row.get("discharge_ts"),
                facility_canonical_id=row.get("facility_canonical_id"),
                facility_name=row.get("facility_name"),
                confidence_score=float(row.get("confidence_score", 0) or 0),
                confidence_flags=row.get("confidence_flags", "").split(",") if row.get("confidence_flags") else [],
                source_systems=row.get("source_systems", "").split(",") if row.get("source_systems") else [],
                events=[],
                has_adt=row.get("has_adt", False),
                has_claims=row.get("has_claims", False),
                has_auth=row.get("has_auth", False),
                payer_id=row.get("payer_id"),
                drg=row.get("drg"),
                principal_diagnosis=row.get("principal_diagnosis"),
                admitting_diagnosis=row.get("admitting_diagnosis"),
                is_readmission=row.get("is_readmission", False),
                transfer_chain=row.get("transfer_chain"),
                los_hours=float(row.get("los_hours", 0) or 0),
            )
            scored_encounters.append(enc)

        context.config["scored_encounters"] = scored_encounters
        context.config["encounters_created"] = 0
        context.config["encounters_updated"] = 0

        # Read prior stage metrics
        try:
            metric_rows = adapter.read_source(
                "asre_run_metrics",
                "SELECT * FROM asre_run_metrics WHERE run_id = :run_id ORDER BY stage_name",
                {"run_id": self.run_id},
            )
            context.config["stage_metrics"] = list(metric_rows) if metric_rows else []
        except Exception:
            context.config["stage_metrics"] = []

        logger.info(
            "Rehydrated %d encounters for resume", len(scored_encounters)
        )

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

            # Also store scored encounters for quality_check stage
            if hasattr(stage, "encounters"):
                context.config["scored_encounters"] = stage.encounters

        elif stage_name == "materialize":
            # Pass materialization counts and stage metrics to quality_check
            if hasattr(stage, "encounters_inserted"):
                context.config["encounters_created"] = stage.encounters_inserted
            if hasattr(stage, "encounters_updated"):
                context.config["encounters_updated"] = stage.encounters_updated
            context.config["stage_metrics"] = list(self.stage_metrics)

        elif stage_name == "quality_check":
            # Convert scored encounters to Encounter objects for episode stitching
            episode_stitch = self._stages.get("episode_stitch")
            scored = context.config.get("scored_encounters", [])
            if scored and hasattr(episode_stitch, "encounters_in"):
                from asre.episode.stage import scored_encounter_to_encounter

                episode_stitch.encounters_in = [  # type: ignore[union-attr]
                    scored_encounter_to_encounter(e) for e in scored
                ]

        elif stage_name == "episode_stitch":
            # Pass episodes to episode materialize
            ep_materialize = self._stages.get("episode_materialize")
            if hasattr(stage, "episodes") and hasattr(ep_materialize, "episodes_in"):
                ep_materialize.episodes_in = stage.episodes  # type: ignore[union-attr]

        elif stage_name == "episode_materialize":
            # Pass episodes to episode quality stage
            ep_quality = self._stages.get("episode_quality")
            ep_stitch = self._stages.get("episode_stitch")
            if (
                ep_stitch is not None
                and hasattr(ep_stitch, "episodes")
                and hasattr(ep_quality, "episodes_in")
            ):
                ep_quality.episodes_in = ep_stitch.episodes  # type: ignore[union-attr]
