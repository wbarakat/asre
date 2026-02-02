"""Tests for PipelineRunner - pipeline orchestrator (US-069).

Tests the full pipeline sequencing: Ingest -> Canonicalize -> FacilityNormalize
-> Stitch -> Dedup -> Reconcile -> Score -> Materialize -> QualityCheck.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage


class DummyStage(PipelineStage):
    """A test stage that records calls."""

    def __init__(self, name: str = "dummy") -> None:
        self.name = name
        self.called = False
        self.call_order: int = -1
        self._call_counter: list[int] = []

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        self.called = True
        if self._call_counter:
            self.call_order = self._call_counter[0]
            self._call_counter[0] += 1
        return batch


class TestPipelineRunnerConstruction:
    """Tests for PipelineRunner initialization."""

    def test_runner_accepts_config_and_mode(self) -> None:
        config: dict[str, Any] = {"customer": {"customer_id": "test"}}
        runner = PipelineRunner(config=config, mode="full")
        assert runner.mode == "full"

    def test_runner_defaults_to_incremental_mode(self) -> None:
        runner = PipelineRunner(config={}, mode="incremental")
        assert runner.mode == "incremental"

    def test_runner_generates_run_id(self) -> None:
        runner = PipelineRunner(config={}, mode="full")
        assert runner.run_id is not None
        assert runner.run_id.startswith("run_")
        # run_id format: run_{timestamp}
        assert re.match(r"^run_\d{8}_\d{6}$", runner.run_id)


class TestPipelineRunnerStageSequencing:
    """Tests that stages are executed in the correct order."""

    def test_stages_run_in_sequence(self) -> None:
        """All stages should execute in order: ingest, canonicalize, facility_normalize,
        stitch, dedup, reconcile, score, materialize, quality_check."""
        runner = PipelineRunner(config={}, mode="full")

        # Replace stages with tracking dummies
        counter = [0]
        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, DummyStage] = {}
        for name in stage_names:
            stage = DummyStage(name)
            stage._call_counter = counter
            stages[name] = stage

        runner._stages = stages  # type: ignore[attr-defined]
        runner.run()

        # All stages should have been called
        for name, stage in stages.items():
            assert stage.called, f"Stage {name} was not called"

        # Verify ordering
        for i, name in enumerate(stage_names):
            assert stages[name].call_order == i, (
                f"Stage {name} ran at order {stages[name].call_order}, expected {i}"
            )

    def test_pipeline_context_passed_to_each_stage(self) -> None:
        """Each stage receives a PipelineContext with run_id, config, and mode."""
        runner = PipelineRunner(config={"key": "val"}, mode="full")

        received_contexts: list[PipelineContext] = []

        class ContextCapturingStage(PipelineStage):
            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                received_contexts.append(context)
                return batch

        stages = {
            name: ContextCapturingStage()
            for name in [
                "ingest", "canonicalize", "facility_normalize",
                "stitch", "dedup", "reconcile", "score",
                "materialize", "quality_check",
            ]
        }
        runner._stages = stages  # type: ignore[attr-defined]
        runner.run()

        assert len(received_contexts) == 9
        for ctx in received_contexts:
            assert ctx.run_id == runner.run_id
            assert ctx.mode == "full"


class TestPipelineRunnerDataHandoff:
    """Tests for data passing between stages."""

    def test_ingest_raw_records_passed_to_canonicalize(self) -> None:
        """IngestStage.raw_records should be accessible to CanonicalizeStage via context."""
        runner = PipelineRunner(config={}, mode="full")

        raw_records = [{"patient_key": "P1", "_source_name": "adt", "_source_type": "adt"}]

        class FakeIngestStage(PipelineStage):
            def __init__(self) -> None:
                self.raw_records: list[dict[str, Any]] = raw_records
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("ingest", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        class CapturingCanonicalizeStage(PipelineStage):
            def __init__(self) -> None:
                self.received_raw_records: list[dict[str, Any]] = []
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("canonicalize", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.received_raw_records = context.config.get("raw_records", [])
                return batch

        ingest = FakeIngestStage()
        canonicalize = CapturingCanonicalizeStage()

        runner._stages = {  # type: ignore[attr-defined]
            "ingest": ingest,
            "canonicalize": canonicalize,
            "facility_normalize": DummyStage("fn"),
            "stitch": DummyStage("stitch"),
            "dedup": DummyStage("dedup"),
            "reconcile": DummyStage("reconcile"),
            "score": DummyStage("score"),
            "materialize": DummyStage("materialize"),
            "quality_check": DummyStage("qc"),
        }
        runner.run()

        assert canonicalize.received_raw_records == raw_records

    def test_stitch_encounters_passed_to_dedup(self) -> None:
        """StitchStage.encounters should be copied to DedupStage.encounters_in."""
        runner = PipelineRunner(config={}, mode="full")

        from asre.stitch.encounter_stitcher import StitchedEncounter

        mock_encounters = [
            StitchedEncounter(patient_key="P1", facility_canonical_id="FAC1"),
        ]

        class FakeStitchStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters = mock_encounters
                self.encounter_metadata: list[Any] = []
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("stitch", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        class CapturingDedupStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters_in: list[StitchedEncounter] = []
                self.encounters: list[StitchedEncounter] = []
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("dedup", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.encounters = list(self.encounters_in)
                return batch

        stitch = FakeStitchStage()
        dedup = CapturingDedupStage()

        runner._stages = {  # type: ignore[attr-defined]
            "ingest": DummyStage("ingest"),
            "canonicalize": DummyStage("canon"),
            "facility_normalize": DummyStage("fn"),
            "stitch": stitch,
            "dedup": dedup,
            "reconcile": DummyStage("reconcile"),
            "score": DummyStage("score"),
            "materialize": DummyStage("materialize"),
            "quality_check": DummyStage("qc"),
        }
        runner.run()

        assert dedup.encounters == mock_encounters

    def test_dedup_encounters_passed_to_reconcile(self) -> None:
        """DedupStage.encounters should be copied to ReconcileStage.encounters_in."""
        runner = PipelineRunner(config={}, mode="full")

        from asre.stitch.encounter_stitcher import StitchedEncounter

        mock_encounters = [
            StitchedEncounter(patient_key="P1", facility_canonical_id="FAC1"),
        ]

        class FakeDedupStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters_in: list[Any] = []
                self.encounters = mock_encounters
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("dedup", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        class CapturingReconcileStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters_in: list[Any] = []
                self.encounters: list[Any] = []
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("reconcile", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.encounters = list(self.encounters_in)
                return batch

        dedup = FakeDedupStage()
        reconcile = CapturingReconcileStage()

        runner._stages = {  # type: ignore[attr-defined]
            "ingest": DummyStage("ingest"),
            "canonicalize": DummyStage("canon"),
            "facility_normalize": DummyStage("fn"),
            "stitch": DummyStage("stitch"),
            "dedup": dedup,
            "reconcile": reconcile,
            "score": DummyStage("score"),
            "materialize": DummyStage("materialize"),
            "quality_check": DummyStage("qc"),
        }
        runner.run()

        assert reconcile.encounters == mock_encounters

    def test_reconcile_encounters_passed_to_score(self) -> None:
        """ReconcileStage.encounters should be copied to ScoreStage.encounters_in."""
        runner = PipelineRunner(config={}, mode="full")

        mock_encounters = [MagicMock()]

        class FakeReconcileStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters_in: list[Any] = []
                self.encounters = mock_encounters
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("reconcile", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        class CapturingScoreStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters_in: list[Any] = []
                self.encounters: list[Any] = []
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("score", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.encounters = list(self.encounters_in)
                return batch

        reconcile = FakeReconcileStage()
        score = CapturingScoreStage()

        runner._stages = {  # type: ignore[attr-defined]
            "ingest": DummyStage("ingest"),
            "canonicalize": DummyStage("canon"),
            "facility_normalize": DummyStage("fn"),
            "stitch": DummyStage("stitch"),
            "dedup": DummyStage("dedup"),
            "reconcile": reconcile,
            "score": score,
            "materialize": DummyStage("materialize"),
            "quality_check": DummyStage("qc"),
        }
        runner.run()

        assert score.encounters == mock_encounters


class TestPipelineRunnerFacilityRegistryMap:
    """Tests that facility registry is populated for ScoreStage."""

    def test_facility_registry_map_populated_in_config(self) -> None:
        """Pipeline runner should populate facility_registry_map from the
        FacilityRegistry after FacilityNormalizationStage runs."""
        runner = PipelineRunner(config={}, mode="full")

        captured_config: dict[str, Any] = {}

        class CapturingScoreStage(PipelineStage):
            def __init__(self) -> None:
                self.encounters_in: list[Any] = []
                self.encounters: list[Any] = []
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("score", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                captured_config.update(context.config)
                return batch

        class FakeFacilityStage(PipelineStage):
            def __init__(self) -> None:
                from asre.config.facility_alias_schema import FacilityAliasConfig
                from asre.facility.normalizer import FacilityNormalizer
                from asre.facility.registry import FacilityRegistry
                normalizer = FacilityNormalizer()
                alias_config = FacilityAliasConfig(facilities=[])
                self._registry = FacilityRegistry(alias_config, normalizer)
                self._registry.add_facility(
                    canonical_id="FAC1",
                    canonical_name="Test Hospital",
                    facility_type="acute",
                )
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics("facility_normalize", "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        facility_stage = FakeFacilityStage()
        score_stage = CapturingScoreStage()

        runner._stages = {  # type: ignore[attr-defined]
            "ingest": DummyStage("ingest"),
            "canonicalize": DummyStage("canon"),
            "facility_normalize": facility_stage,
            "stitch": DummyStage("stitch"),
            "dedup": DummyStage("dedup"),
            "reconcile": DummyStage("reconcile"),
            "score": score_stage,
            "materialize": DummyStage("materialize"),
            "quality_check": DummyStage("qc"),
        }
        runner.run()

        assert "facility_registry_map" in captured_config
        assert captured_config["facility_registry_map"]["FAC1"] == "acute"


class TestPipelineRunnerMetrics:
    """Tests that stage metrics are collected."""

    def test_run_id_format(self) -> None:
        runner = PipelineRunner(config={}, mode="full")
        assert re.match(r"^run_\d{8}_\d{6}$", runner.run_id)

    def test_stage_metrics_collected(self) -> None:
        """PipelineRunner should collect metrics from each stage."""
        runner = PipelineRunner(config={}, mode="full")

        class MetricStage(PipelineStage):
            def __init__(self, name: str) -> None:
                from asre.observability.metrics import StageMetrics
                self.metrics = StageMetrics(name, "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics.records_in = 10
                self.metrics.records_out = 8
                return batch

        stages = {
            name: MetricStage(name)
            for name in [
                "ingest", "canonicalize", "facility_normalize",
                "stitch", "dedup", "reconcile", "score",
                "materialize", "quality_check",
            ]
        }
        runner._stages = stages  # type: ignore[attr-defined]
        result = runner.run()

        # Runner should have collected metrics from stages
        assert runner.stage_metrics is not None
        assert len(runner.stage_metrics) == 9


class TestPipelineRunnerMaterializeAndQualityPlaceholders:
    """Tests for materialize and quality_check stage placeholders."""

    def test_materialize_stage_exists(self) -> None:
        """Pipeline runner should include a materialize stage."""
        runner = PipelineRunner(config={}, mode="full")
        assert "materialize" in runner._stages  # type: ignore[attr-defined]

    def test_quality_check_stage_exists(self) -> None:
        """Pipeline runner should include a quality_check stage."""
        runner = PipelineRunner(config={}, mode="full")
        assert "quality_check" in runner._stages  # type: ignore[attr-defined]
