"""Tests for dry-run mode (US-104).

Pipeline runs all stages but skips materialization (no writes to output tables).
Logs what would be written (encounter counts, metric values).
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from asre.cli.main import cli
from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage


class DummyStage(PipelineStage):
    """Test stage that records calls."""

    def __init__(self, name: str = "dummy") -> None:
        self.name = name
        self.called = False
        from asre.observability.metrics import StageMetrics

        self.metrics = StageMetrics(name, "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        self.called = True
        return batch


class TestPipelineRunnerDryRun:
    """Tests for dry-run mode in PipelineRunner."""

    def test_dry_run_flag_in_config(self) -> None:
        """PipelineRunner accepts dry_run in config and propagates it to context."""
        config: dict[str, Any] = {"dry_run": True}
        runner = PipelineRunner(config=config, mode="full")

        stages: dict[str, PipelineStage] = OrderedDict()
        stage = DummyStage("only")
        stages["only"] = stage
        runner._stages = stages  # type: ignore[attr-defined]
        runner.run()

        assert stage.called

    def test_dry_run_skips_materialize_writes(self) -> None:
        """MaterializeStage should skip DB writes when dry_run=True."""
        from asre.materialize.stage import MaterializeStage
        from asre.reconcile.stage import ReconciledEncounter
        from asre.stitch.encounter_stitcher import StitchedEncounter

        stage = MaterializeStage()

        # Create a mock encounter
        mock_event = MagicMock()
        mock_event.event_id = "evt1"
        mock_event.event_type = "ADMIT"
        mock_event.event_ts = MagicMock()
        mock_event.source_system = "adt_vendor"
        mock_event.role_in_encounter = None
        mock_event.patient_class = "inpatient"
        mock_event.facility_canonical_id = "FAC_001"

        stitched = MagicMock(spec=StitchedEncounter)
        stitched.encounter_id = "enc_001"
        stitched.patient_key = "PAT_001"
        stitched.events = [mock_event]
        stitched.status = "open"
        stitched.encounter_type = "inpatient"
        stitched.facility_canonical_id = "FAC_001"
        stitched.obs_to_ip_conversion = False
        stitched.transfer_chain = []
        stitched.has_discharge = False
        stitched.confidence_score = 0.85
        stitched.confidence_flags = ["HAS_ADT_ADMIT"]

        enc = ReconciledEncounter(stitched)
        enc.confidence_score = 0.85
        enc.confidence_flags = ["HAS_ADT_ADMIT"]

        stage.encounters_in = [enc]

        adapter = MagicMock()
        context = PipelineContext(
            run_id="test_dry",
            config={"adapter": adapter, "dry_run": True},
            mode="full",
        )
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, context)

        # Adapter should NOT have been called for writes
        adapter.write_records.assert_not_called()
        adapter.execute_ddl.assert_not_called()

        # But metrics should still be populated
        assert stage.metrics.records_in == 1

    def test_dry_run_logs_what_would_be_written(self) -> None:
        """MaterializeStage should log encounter counts in dry-run mode."""
        from asre.materialize.stage import MaterializeStage
        from asre.reconcile.stage import ReconciledEncounter
        from asre.stitch.encounter_stitcher import StitchedEncounter

        stage = MaterializeStage()

        mock_event = MagicMock()
        mock_event.event_id = "evt1"
        mock_event.event_type = "ADMIT"
        mock_event.event_ts = MagicMock()
        mock_event.source_system = "adt_vendor"
        mock_event.role_in_encounter = None
        mock_event.patient_class = "inpatient"
        mock_event.facility_canonical_id = "FAC_001"

        stitched = MagicMock(spec=StitchedEncounter)
        stitched.encounter_id = "enc_001"
        stitched.patient_key = "PAT_001"
        stitched.events = [mock_event]
        stitched.status = "open"
        stitched.encounter_type = "inpatient"
        stitched.facility_canonical_id = "FAC_001"
        stitched.obs_to_ip_conversion = False
        stitched.transfer_chain = []
        stitched.has_discharge = False
        stitched.confidence_score = 0.85
        stitched.confidence_flags = ["HAS_ADT_ADMIT"]

        enc = ReconciledEncounter(stitched)
        enc.confidence_score = 0.85
        enc.confidence_flags = ["HAS_ADT_ADMIT"]

        stage.encounters_in = [enc]

        adapter = MagicMock()
        context = PipelineContext(
            run_id="test_dry",
            config={"adapter": adapter, "dry_run": True},
            mode="full",
        )
        batch = EventBatch(batch_id="test", events=[])

        import logging

        with patch("asre.materialize.stage.logger") as mock_logger:
            stage.run(batch, context)
            # Should log dry-run info
            log_messages = [
                str(call) for call in mock_logger.info.call_args_list
            ]
            dry_run_logged = any("dry" in msg.lower() for msg in log_messages)
            assert dry_run_logged, f"Expected dry-run log message, got: {log_messages}"

    def test_dry_run_quality_stage_skips_writes(self) -> None:
        """QualityCheckStage should skip DB writes when dry_run=True."""
        from asre.quality.stage import QualityCheckStage

        stage = QualityCheckStage()

        adapter = MagicMock()
        context = PipelineContext(
            run_id="test_dry",
            config={
                "adapter": adapter,
                "dry_run": True,
                "scored_encounters": [],
                "stage_metrics": [],
                "encounters_created": 0,
                "encounters_updated": 0,
            },
            mode="full",
        )
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, context)

        # Adapter should NOT have been called for writes
        adapter.write_records.assert_not_called()
        adapter.execute_ddl.assert_not_called()
        adapter.set_watermark.assert_not_called()

    def test_dry_run_episode_materialize_skips_writes(self) -> None:
        """EpisodeMaterializeStage should skip DB writes when dry_run=True."""
        from asre.episode.stage import EpisodeMaterializeStage
        from asre.models.episode import Episode

        stage = EpisodeMaterializeStage()

        episode = Episode(
            episode_id="ep_001",
            patient_key="PAT_001",
            episode_type="medical",
            episode_status="closed",
            episode_start_ts=None,
            episode_end_ts=None,
            total_los_days=None,
            encounter_ids=["enc_001"],
            encounter_count=1,
            facility_count=1,
            facility_sequence=["FAC_001"],
            includes_readmission=False,
            includes_post_acute=False,
            is_acute=True,
            principal_diagnosis=None,
            diagnosis_codes=[],
            confidence_score=0.85,
            created_at=None,
            updated_at=None,
        )
        stage.episodes_in = [episode]

        adapter = MagicMock()
        context = PipelineContext(
            run_id="test_dry",
            config={"adapter": adapter, "dry_run": True},
            mode="full",
        )
        batch = EventBatch(batch_id="test", events=[])

        stage.run(batch, context)

        # Adapter should NOT have been called for writes
        adapter.write_records.assert_not_called()
        adapter.execute_ddl.assert_not_called()

    def test_dry_run_all_processing_stages_still_run(self) -> None:
        """All stages execute in dry-run, only materialization is skipped."""
        config: dict[str, Any] = {"dry_run": True}
        runner = PipelineRunner(config=config, mode="full")

        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, DummyStage] = OrderedDict()
        for name in stage_names:
            stages[name] = DummyStage(name)

        runner._stages = stages  # type: ignore[attr-defined]
        result = runner.run()

        # All stages should have been called (processing still happens)
        for name, stage in stages.items():
            assert stage.called, f"Stage {name} should have been called"


class TestCliDryRun:
    """Tests for --dry-run CLI flag and ASRE_DRY_RUN env var."""

    _VALID_CONFIG_YAML = (
        "customer:\n"
        "  customer_id: test_customer\n"
        "  customer_name: Test Customer\n"
        "warehouse:\n"
        "  type: postgres\n"
        "  connection:\n"
        "    host: localhost\n"
        "    database: test\n"
    )

    @patch("asre.cli.main._validate_license_or_exit")
    @patch("asre.cli.main._create_pipeline_runner")
    def test_dry_run_flag_passed_to_runner(
        self, mock_create: MagicMock, _mock_license: MagicMock, tmp_path: Path
    ) -> None:
        """--dry-run flag should result in dry_run=True in pipeline config."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = {
            "run_id": "test_run",
            "mode": "full",
            "stages_completed": 9,
        }
        mock_create.return_value = mock_runner

        customer_dir = tmp_path / "test_customer"
        customer_dir.mkdir()
        (customer_dir / "config.yaml").write_text(self._VALID_CONFIG_YAML)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--mode", "full",
                "--dry-run",
                "--config-path", str(tmp_path),
                "--customer-id", "test_customer",
            ],
        )

        assert result.exit_code == 0
        # Verify _create_pipeline_runner was called with dry_run=True
        call_kwargs = mock_create.call_args
        assert call_kwargs is not None
        # Check dry_run parameter
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("dry_run") is True
        else:
            # Positional args: config_path, customer_id, mode, dry_run
            assert len(call_kwargs.args) >= 4
            assert call_kwargs.args[3] is True

    @patch("asre.cli.main._validate_license_or_exit")
    @patch("asre.cli.main._create_pipeline_runner")
    def test_dry_run_env_var(
        self, mock_create: MagicMock, _mock_license: MagicMock, tmp_path: Path
    ) -> None:
        """ASRE_DRY_RUN=true should enable dry-run mode."""
        mock_runner = MagicMock()
        mock_runner.run.return_value = {
            "run_id": "test_run",
            "mode": "full",
            "stages_completed": 9,
        }
        mock_create.return_value = mock_runner

        customer_dir = tmp_path / "test_customer"
        customer_dir.mkdir()
        (customer_dir / "config.yaml").write_text(self._VALID_CONFIG_YAML)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                "--mode", "full",
                "--config-path", str(tmp_path),
                "--customer-id", "test_customer",
            ],
            env={"ASRE_DRY_RUN": "true"},
        )

        assert result.exit_code == 0
        call_kwargs = mock_create.call_args
        assert call_kwargs is not None
        if call_kwargs.kwargs:
            assert call_kwargs.kwargs.get("dry_run") is True
        else:
            assert len(call_kwargs.args) >= 4
            assert call_kwargs.args[3] is True


class TestDryRunIntegrationWithRunner:
    """Integration test: dry run produces logs but no table changes."""

    def test_dry_run_produces_summary_no_writes(self) -> None:
        """Full pipeline in dry-run mode produces result summary but no DB writes."""
        adapter = MagicMock()
        config: dict[str, Any] = {
            "dry_run": True,
            "adapter": adapter,
        }
        runner = PipelineRunner(config=config, mode="full")

        # Replace all stages with dummies
        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, DummyStage] = OrderedDict()
        for name in stage_names:
            stages[name] = DummyStage(name)

        runner._stages = stages  # type: ignore[attr-defined]
        result = runner.run()

        assert result["run_id"] is not None
        assert result["mode"] == "full"
