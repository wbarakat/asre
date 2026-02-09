"""Tests for IngestStage - pipeline stage for data ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from asre.ingest.stage import IngestStage
from asre.config.source_schema import SourceConfig
from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineStage


class TestIngestStageInterface:
    """Test that IngestStage implements PipelineStage."""

    def test_is_pipeline_stage_subclass(self) -> None:
        assert issubclass(IngestStage, PipelineStage)

    def test_can_instantiate(self) -> None:
        stage = IngestStage()
        assert isinstance(stage, PipelineStage)


class TestIngestStageRun:
    """Test IngestStage.run() orchestration."""

    @pytest.fixture()
    def mock_adapter(self) -> MagicMock:
        """Mock IngestAdapter with read_source and watermark methods."""
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.get_watermark.return_value = None
        return adapter

    @pytest.fixture()
    def adt_source_config(self) -> dict[str, Any]:
        """Minimal ADT source config dict matching SourceConfig shape."""
        return {
            "name": "adt_vendor_x",
            "type": "adt",
            "source": {
                "table": "raw_adt_events",
                "incremental_key": "message_ts",
            },
            "field_mappings": {
                "patient_key": "patient_id",
                "event_ts": "message_ts",
                "source_record_id": "msg_control_id",
                "facility_raw": "sending_facility",
            },
            "event_type_rules": {
                "source_field": "hl7_event",
                "mappings": {"A01": "ADMIT", "A03": "DISCHARGE"},
            },
            "filters": {"exclude": None},
        }

    @pytest.fixture()
    def claims_source_config(self) -> dict[str, Any]:
        """Minimal claims source config dict."""
        return {
            "name": "claims_clearinghouse",
            "type": "claims",
            "source": {
                "table": "raw_claims",
                "incremental_key": "received_ts",
            },
            "field_mappings": {
                "patient_key": "member_id",
                "event_ts": "admission_date",
                "source_record_id": "claim_id",
                "facility_raw": "facility_name",
            },
            "event_type_rules": {
                "source_field": "claim_type",
                "mappings": {},
            },
            "paired_events": {
                "admit": {"event_ts": "admission_date", "event_type": "CLAIM_ADMIT"},
                "discharge": {"event_ts": "discharge_date", "event_type": "CLAIM_DISCHARGE"},
            },
            "filters": None,
        }

    @pytest.fixture()
    def pipeline_context(
        self, mock_adapter: MagicMock, adt_source_config: dict[str, Any]
    ) -> PipelineContext:
        """PipelineContext with one ADT source and adapter."""
        return PipelineContext(
            run_id="run_20260202_001",
            config={
                "sources": [adt_source_config],
                "schedule": {
                    "mode": "full",
                    "lookback_buffer": {"default": "24h"},
                },
                "adapter": mock_adapter,
            },
            mode="full",
        )

    def test_iterates_over_all_configured_sources(
        self,
        mock_adapter: MagicMock,
        adt_source_config: dict[str, Any],
        claims_source_config: dict[str, Any],
    ) -> None:
        """IngestStage reads from each configured source."""
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [adt_source_config, claims_source_config],
                "schedule": {
                    "mode": "full",
                    "lookback_buffer": {"default": "24h"},
                },
                "adapter": mock_adapter,
            },
            mode="full",
        )
        mock_adapter.read_source.return_value = []

        stage = IngestStage()
        result = stage.run(EventBatch(batch_id="b1", events=[]), context)

        assert mock_adapter.read_source.call_count == 2

    def test_accepts_source_config_models(
        self,
        mock_adapter: MagicMock,
        adt_source_config: dict[str, Any],
    ) -> None:
        """IngestStage should accept SourceConfig objects from load_config."""
        source_model = SourceConfig(**adt_source_config)
        context = PipelineContext(
            run_id="run_model",
            config={
                "sources": [source_model],
                "schedule": {
                    "mode": "full",
                    "lookback_buffer": {"default": "24h"},
                },
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        mock_adapter.read_source.assert_called_once()

    def test_returns_raw_records_in_result(
        self,
        mock_adapter: MagicMock,
        pipeline_context: PipelineContext,
    ) -> None:
        """IngestStage stores raw records accessible from the result."""
        raw_records = [
            {"patient_id": "P001", "msg_control_id": "R1", "message_ts": "2026-01-01T10:00:00"},
            {"patient_id": "P002", "msg_control_id": "R2", "message_ts": "2026-01-01T11:00:00"},
        ]
        mock_adapter.read_source.return_value = raw_records

        stage = IngestStage()
        result = stage.run(EventBatch(batch_id="b1", events=[]), pipeline_context)

        # IngestStage should expose raw_records on itself after run
        assert len(stage.raw_records) == 2
        assert stage.raw_records[0]["patient_id"] == "P001"
        assert stage.raw_records[1]["patient_id"] == "P002"

    def test_preserves_raw_payload(
        self,
        mock_adapter: MagicMock,
        pipeline_context: PipelineContext,
    ) -> None:
        """Each record should have _raw_payload set to the original source record."""
        original_record = {"patient_id": "P001", "msg_control_id": "R1", "hl7_event": "A01"}
        mock_adapter.read_source.return_value = [original_record]

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), pipeline_context)

        record = stage.raw_records[0]
        assert record["_raw_payload"] == original_record

    def test_preserves_source_name_on_records(
        self,
        mock_adapter: MagicMock,
        pipeline_context: PipelineContext,
    ) -> None:
        """Each record should have _source_name set so downstream knows which source it came from."""
        mock_adapter.read_source.return_value = [
            {"patient_id": "P001", "msg_control_id": "R1"},
        ]

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), pipeline_context)

        assert stage.raw_records[0]["_source_name"] == "adt_vendor_x"

    def test_preserves_source_type_on_records(
        self,
        mock_adapter: MagicMock,
        pipeline_context: PipelineContext,
    ) -> None:
        """Each record should have _source_type set for routing in canonicalize stage."""
        mock_adapter.read_source.return_value = [
            {"patient_id": "P001", "msg_control_id": "R1"},
        ]

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), pipeline_context)

        assert stage.raw_records[0]["_source_type"] == "adt"

    def test_dedup_by_source_record_id(
        self,
        mock_adapter: MagicMock,
        pipeline_context: PipelineContext,
    ) -> None:
        """Duplicate source_record_ids within a source batch are collapsed."""
        mock_adapter.read_source.return_value = [
            {"patient_id": "P001", "msg_control_id": "R1", "message_ts": "2026-01-01T10:00:00"},
            {"patient_id": "P002", "msg_control_id": "R1", "message_ts": "2026-01-01T11:00:00"},
            {"patient_id": "P003", "msg_control_id": "R2", "message_ts": "2026-01-01T12:00:00"},
        ]

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), pipeline_context)

        # R1 appears twice, should keep first
        assert len(stage.raw_records) == 2
        assert stage.raw_records[0]["patient_id"] == "P001"
        assert stage.raw_records[1]["patient_id"] == "P003"

    def test_ingest_orders_by_incremental_key_and_source_record_id(
        self,
        mock_adapter: MagicMock,
        adt_source_config: dict[str, Any],
    ) -> None:
        """IngestStage should add ORDER BY for deterministic reads."""
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [adt_source_config],
                "schedule": {
                    "mode": "full",
                    "lookback_buffer": {"default": "24h"},
                },
                "adapter": mock_adapter,
            },
            mode="full",
        )
        mock_adapter.read_source.return_value = []

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        query = mock_adapter.read_source.call_args[0][1]
        assert "ORDER BY message_ts, msg_control_id" in query

    def test_returns_event_batch_passthrough(
        self,
        mock_adapter: MagicMock,
        pipeline_context: PipelineContext,
    ) -> None:
        """run() returns an EventBatch (empty, since raw records aren't canonical yet)."""
        mock_adapter.read_source.return_value = [
            {"patient_id": "P001", "msg_control_id": "R1"},
        ]

        stage = IngestStage()
        result = stage.run(EventBatch(batch_id="b1", events=[]), pipeline_context)

        assert isinstance(result, EventBatch)
        # Events are empty because raw records aren't CanonicalEvents yet
        assert len(result.events) == 0
        assert result.batch_id == "b1"


class TestIngestStageMetrics:
    """Test that IngestStage records correct stage metrics."""

    @pytest.fixture()
    def mock_adapter(self) -> MagicMock:
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.get_watermark.return_value = None
        return adapter

    @pytest.fixture()
    def source_config(self) -> dict[str, Any]:
        return {
            "name": "adt_vendor_x",
            "type": "adt",
            "source": {
                "table": "raw_adt_events",
                "incremental_key": "message_ts",
            },
            "field_mappings": {
                "patient_key": "patient_id",
                "event_ts": "message_ts",
                "source_record_id": "msg_control_id",
            },
            "event_type_rules": {
                "source_field": "hl7_event",
                "mappings": {},
            },
            "filters": None,
        }

    def test_records_in_counts_source_records(
        self,
        mock_adapter: MagicMock,
        source_config: dict[str, Any],
    ) -> None:
        """records_in should count total records read from all sources (before dedup)."""
        mock_adapter.read_source.return_value = [
            {"patient_id": "P001", "msg_control_id": "R1"},
            {"patient_id": "P002", "msg_control_id": "R2"},
            {"patient_id": "P003", "msg_control_id": "R3"},
        ]
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config],
                "schedule": {"mode": "full", "lookback_buffer": {"default": "24h"}},
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        assert stage.metrics.records_in == 3

    def test_records_out_counts_after_dedup(
        self,
        mock_adapter: MagicMock,
        source_config: dict[str, Any],
    ) -> None:
        """records_out should count records after dedup/filter."""
        mock_adapter.read_source.return_value = [
            {"patient_id": "P001", "msg_control_id": "R1"},
            {"patient_id": "P002", "msg_control_id": "R1"},  # duplicate
            {"patient_id": "P003", "msg_control_id": "R2"},
        ]
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config],
                "schedule": {"mode": "full", "lookback_buffer": {"default": "24h"}},
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        assert stage.metrics.records_in == 3
        assert stage.metrics.records_out == 2

    def test_metrics_across_multiple_sources(
        self,
        mock_adapter: MagicMock,
        source_config: dict[str, Any],
    ) -> None:
        """Metrics should aggregate across all sources."""
        source2 = dict(source_config)
        source2 = {**source_config, "name": "claims_source", "type": "claims"}
        source2["event_type_rules"] = {"source_field": "type", "mappings": {}}
        source2["paired_events"] = {
            "admit": {"event_ts": "admit_date", "event_type": "CLAIM_ADMIT"},
            "discharge": {"event_ts": "discharge_date", "event_type": "CLAIM_DISCHARGE"},
        }

        # First source returns 3 records, second returns 2
        mock_adapter.read_source.side_effect = [
            [
                {"patient_id": "P001", "msg_control_id": "R1"},
                {"patient_id": "P002", "msg_control_id": "R2"},
                {"patient_id": "P003", "msg_control_id": "R3"},
            ],
            [
                {"member_id": "P004", "claim_id": "C1"},
                {"member_id": "P005", "claim_id": "C2"},
            ],
        ]
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config, source2],
                "schedule": {"mode": "full", "lookback_buffer": {"default": "24h"}},
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        assert stage.metrics.records_in == 5
        assert stage.metrics.records_out == 5
        assert len(stage.raw_records) == 5

    def test_errors_tracked_on_read_failure(
        self,
        mock_adapter: MagicMock,
        source_config: dict[str, Any],
    ) -> None:
        """If a source read fails, error count is incremented but pipeline continues."""
        mock_adapter.read_source.side_effect = Exception("Connection lost")
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config],
                "schedule": {"mode": "full", "lookback_buffer": {"default": "24h"}},
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        assert stage.metrics.errors == 1
        assert len(stage.raw_records) == 0


class TestIngestStageQueryBuilding:
    """Test that IngestStage builds correct queries for different modes."""

    @pytest.fixture()
    def mock_adapter(self) -> MagicMock:
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.get_watermark.return_value = None
        return adapter

    @pytest.fixture()
    def source_config_with_filter(self) -> dict[str, Any]:
        return {
            "name": "adt_vendor_x",
            "type": "adt",
            "source": {
                "table": "raw_adt_events",
                "incremental_key": "message_ts",
            },
            "field_mappings": {
                "patient_key": "patient_id",
                "event_ts": "message_ts",
                "source_record_id": "msg_control_id",
            },
            "event_type_rules": {
                "source_field": "hl7_event",
                "mappings": {},
            },
            "filters": {"exclude": "hl7_event IN ('A08', 'A31')"},
        }

    def test_full_mode_no_watermark_filter(
        self,
        mock_adapter: MagicMock,
        source_config_with_filter: dict[str, Any],
    ) -> None:
        """Full mode should not include watermark in query."""
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config_with_filter],
                "schedule": {"mode": "full", "lookback_buffer": {"default": "24h"}},
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        call_args = mock_adapter.read_source.call_args
        query = call_args[1]["query"] if "query" in (call_args[1] or {}) else call_args[0][1]
        assert "watermark" not in query.lower() or ":watermark" not in query

    def test_incremental_mode_with_watermark(
        self,
        mock_adapter: MagicMock,
        source_config_with_filter: dict[str, Any],
    ) -> None:
        """Incremental mode with existing watermark should add watermark filter."""
        mock_adapter.get_watermark.return_value = datetime(2026, 1, 1, tzinfo=timezone.utc)
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config_with_filter],
                "schedule": {
                    "mode": "incremental",
                    "lookback_buffer": {"default": "24h"},
                },
                "adapter": mock_adapter,
            },
            mode="incremental",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        call_args = mock_adapter.read_source.call_args
        query = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["query"]
        assert ":watermark" in query

    def test_exclude_filter_applied(
        self,
        mock_adapter: MagicMock,
        source_config_with_filter: dict[str, Any],
    ) -> None:
        """Exclude filter from source config should appear in query."""
        context = PipelineContext(
            run_id="run_001",
            config={
                "sources": [source_config_with_filter],
                "schedule": {"mode": "full", "lookback_buffer": {"default": "24h"}},
                "adapter": mock_adapter,
            },
            mode="full",
        )

        stage = IngestStage()
        stage.run(EventBatch(batch_id="b1", events=[]), context)

        call_args = mock_adapter.read_source.call_args
        query = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["query"]
        assert "A08" in query
        assert "A31" in query
