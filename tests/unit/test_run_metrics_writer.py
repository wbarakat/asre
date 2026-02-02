"""Tests for RunMetricsWriter - writes per-stage metrics to asre_run_metrics (US-076)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

from asre.observability.metrics import StageMetrics
from asre.observability.run_metrics_writer import RunMetricsWriter, RUN_METRICS_TABLE


class TestRunMetricsWriterTableCreation:
    """Tests that RunMetricsWriter creates the asre_run_metrics table."""

    def test_ensure_table_creates_run_metrics_table(self) -> None:
        adapter = MagicMock()
        writer = RunMetricsWriter(adapter)
        writer.ensure_table()
        adapter.execute_ddl.assert_called_once()
        ddl: str = adapter.execute_ddl.call_args[0][0]
        assert "asre_run_metrics" in ddl
        assert "CREATE TABLE IF NOT EXISTS" in ddl

    def test_table_has_required_columns(self) -> None:
        adapter = MagicMock()
        writer = RunMetricsWriter(adapter)
        writer.ensure_table()
        ddl: str = adapter.execute_ddl.call_args[0][0]
        for col in ["run_id", "stage_name", "started_at", "completed_at",
                     "records_in", "records_out", "errors", "status"]:
            assert col in ddl, f"Column {col} not found in DDL"

    def test_table_has_composite_primary_key(self) -> None:
        adapter = MagicMock()
        writer = RunMetricsWriter(adapter)
        writer.ensure_table()
        ddl: str = adapter.execute_ddl.call_args[0][0]
        assert "PRIMARY KEY" in ddl


class TestRunMetricsWriterWriteMetrics:
    """Tests that RunMetricsWriter writes metrics records."""

    def test_write_metrics_calls_write_records(self) -> None:
        adapter = MagicMock()
        adapter.write_records.return_value = 1
        writer = RunMetricsWriter(adapter)

        with StageMetrics("ingest", "run_001") as m:
            m.records_in = 100
            m.records_out = 95
            m.errors = 5

        writer.write_metrics([m.to_dict()])
        adapter.write_records.assert_called_once()
        table_name = adapter.write_records.call_args[0][0]
        assert table_name == RUN_METRICS_TABLE

    def test_write_metrics_passes_correct_records(self) -> None:
        adapter = MagicMock()
        adapter.write_records.return_value = 2
        writer = RunMetricsWriter(adapter)

        metrics_list: list[dict[str, Any]] = []
        for name in ["ingest", "canonicalize"]:
            with StageMetrics(name, "run_002") as m:
                m.records_in = 50
                m.records_out = 50
            metrics_list.append(m.to_dict())

        writer.write_metrics(metrics_list)
        records = adapter.write_records.call_args[0][1]
        assert len(records) == 2
        assert records[0]["stage_name"] == "ingest"
        assert records[1]["stage_name"] == "canonicalize"

    def test_write_metrics_preserves_all_fields(self) -> None:
        adapter = MagicMock()
        adapter.write_records.return_value = 1
        writer = RunMetricsWriter(adapter)

        with StageMetrics("score", "run_003") as m:
            m.records_in = 10
            m.records_out = 10
            m.errors = 0

        writer.write_metrics([m.to_dict()])
        records = adapter.write_records.call_args[0][1]
        rec = records[0]
        assert rec["run_id"] == "run_003"
        assert rec["stage_name"] == "score"
        assert rec["records_in"] == 10
        assert rec["records_out"] == 10
        assert rec["errors"] == 0
        assert rec["status"] == "success"
        assert rec["started_at"] is not None
        assert rec["completed_at"] is not None

    def test_write_metrics_with_empty_list_does_nothing(self) -> None:
        adapter = MagicMock()
        writer = RunMetricsWriter(adapter)
        writer.write_metrics([])
        adapter.write_records.assert_not_called()

    def test_write_all_nine_stages(self) -> None:
        """All 9 pipeline stages should produce metrics rows."""
        adapter = MagicMock()
        adapter.write_records.return_value = 9
        writer = RunMetricsWriter(adapter)

        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        metrics_list: list[dict[str, Any]] = []
        for name in stage_names:
            with StageMetrics(name, "run_004") as m:
                m.records_in = 100
                m.records_out = 100
            metrics_list.append(m.to_dict())

        writer.write_metrics(metrics_list)
        records = adapter.write_records.call_args[0][1]
        assert len(records) == 9
        written_names = [r["stage_name"] for r in records]
        assert written_names == stage_names


class TestRunMetricsWriterIntegrationWithRunner:
    """Tests that PipelineRunner persists metrics via RunMetricsWriter."""

    def test_runner_writes_metrics_to_database(self) -> None:
        """After all stages complete, runner should write metrics to asre_run_metrics."""
        from asre.models.batch import EventBatch
        from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage

        adapter = MagicMock()
        adapter.write_records.return_value = 0
        adapter.execute_ddl.return_value = None

        class MetricStage(PipelineStage):
            def __init__(self, name: str) -> None:
                self.metrics = StageMetrics(name, "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics = StageMetrics(self.metrics.stage_name, context.run_id)
                with self.metrics:
                    self.metrics.records_in = 10
                    self.metrics.records_out = 8
                return batch

        runner = PipelineRunner(config={"adapter": adapter}, mode="full")
        stages = {
            name: MetricStage(name)
            for name in [
                "ingest", "canonicalize", "facility_normalize",
                "stitch", "dedup", "reconcile", "score",
                "materialize", "quality_check",
            ]
        }
        runner._stages = stages  # type: ignore[attr-defined]
        runner.run()

        # Verify asre_run_metrics table was created
        ddl_calls = [c[0][0] for c in adapter.execute_ddl.call_args_list]
        assert any("asre_run_metrics" in ddl for ddl in ddl_calls)

        # Verify metrics were written
        write_calls = adapter.write_records.call_args_list
        metrics_writes = [c for c in write_calls if c[0][0] == RUN_METRICS_TABLE]
        assert len(metrics_writes) == 1
        records = metrics_writes[0][0][1]
        assert len(records) == 9

    def test_runner_does_not_write_metrics_without_adapter(self) -> None:
        """Without an adapter, metrics should still be collected but not persisted."""
        from asre.models.batch import EventBatch
        from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage

        class MetricStage(PipelineStage):
            def __init__(self, name: str) -> None:
                self.metrics = StageMetrics(name, "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.metrics.records_in = 5
                self.metrics.records_out = 5
                return batch

        runner = PipelineRunner(config={}, mode="full")
        stages = {
            name: MetricStage(name)
            for name in [
                "ingest", "canonicalize", "facility_normalize",
                "stitch", "dedup", "reconcile", "score",
                "materialize", "quality_check",
            ]
        }
        runner._stages = stages  # type: ignore[attr-defined]
        # Should not raise even without adapter
        result = runner.run()
        assert len(runner.stage_metrics) == 9
