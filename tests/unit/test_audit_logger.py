"""Tests for audit logging (US-075).

Tests that all encounter modifications are tracked in asre_audit_log
with proper fields and actions per pipeline stage.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext, PipelineRunner, PipelineStage


class TestAuditLoggerCreation:
    """Tests for AuditLogger class instantiation and log entry creation."""

    def test_audit_logger_creates_log_entry(self) -> None:
        """AuditLogger.log() should create a log entry with required fields."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_20250101_120000")
        logger.log(
            action="materialize",
            entity_type="encounter",
            entity_id="enc_001",
            detail="Created new encounter",
        )

        adapter.write_records.assert_called_once()
        call_args = adapter.write_records.call_args
        assert call_args[0][0] == "asre_audit_log"
        records = call_args[0][1]
        assert len(records) == 1

        record = records[0]
        assert record["run_id"] == "run_20250101_120000"
        assert record["action"] == "materialize"
        assert record["entity_type"] == "encounter"
        assert record["entity_id"] == "enc_001"
        assert record["detail"] == "Created new encounter"

    def test_audit_log_entry_has_log_id(self) -> None:
        """Each audit log entry must have a unique log_id."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(
            action="stitch",
            entity_type="encounter",
            entity_id="enc_001",
            detail="Stitched events",
        )

        record = adapter.write_records.call_args[0][1][0]
        assert "log_id" in record
        assert isinstance(record["log_id"], str)
        assert len(record["log_id"]) > 0

    def test_audit_log_entry_has_timestamp(self) -> None:
        """Each audit log entry must have a timestamp."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(
            action="dedup",
            entity_type="event",
            entity_id="evt_001",
            detail="Marked as duplicate",
        )

        record = adapter.write_records.call_args[0][1][0]
        assert "timestamp" in record
        assert isinstance(record["timestamp"], str)
        # Should be ISO format
        datetime.fromisoformat(record["timestamp"])

    def test_audit_log_entries_have_unique_log_ids(self) -> None:
        """Multiple log entries should have different log_ids."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(action="stitch", entity_type="encounter", entity_id="enc_001", detail="a")
        logger.log(action="stitch", entity_type="encounter", entity_id="enc_002", detail="b")

        id1 = adapter.write_records.call_args_list[0][0][1][0]["log_id"]
        id2 = adapter.write_records.call_args_list[1][0][1][0]["log_id"]
        assert id1 != id2

    def test_audit_log_all_required_fields(self) -> None:
        """Audit log entry must contain all required fields: log_id, run_id, timestamp, action, entity_type, entity_id, detail."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(
            action="reconcile",
            entity_type="encounter",
            entity_id="enc_abc",
            detail="Resolved timestamps",
        )

        record = adapter.write_records.call_args[0][1][0]
        required_fields = {"log_id", "run_id", "timestamp", "action", "entity_type", "entity_id", "detail"}
        assert required_fields.issubset(set(record.keys()))


class TestAuditLoggerActions:
    """Tests for valid audit log actions."""

    @pytest.mark.parametrize(
        "action",
        ["ingest", "stitch", "dedup", "reconcile", "score", "normalize", "materialize"],
    )
    def test_valid_actions(self, action: str) -> None:
        """AuditLogger should accept all documented actions."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(
            action=action,
            entity_type="encounter",
            entity_id="enc_001",
            detail=f"Action: {action}",
        )

        record = adapter.write_records.call_args[0][1][0]
        assert record["action"] == action


class TestAuditLoggerDetail:
    """Tests for detail field content."""

    def test_detail_for_create(self) -> None:
        """For new encounters, detail should describe the creation."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(
            action="materialize",
            entity_type="encounter",
            entity_id="enc_001",
            detail="Created encounter: encounter_type=inpatient, status=closed",
        )

        record = adapter.write_records.call_args[0][1][0]
        assert "Created" in record["detail"]

    def test_detail_for_update_with_old_new(self) -> None:
        """For updates, detail should include old and new values."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.log(
            action="materialize",
            entity_type="encounter",
            entity_id="enc_001",
            detail="Updated encounter: confidence_score 0.65 -> 0.85",
        )

        record = adapter.write_records.call_args[0][1][0]
        assert "Updated" in record["detail"]
        assert "->" in record["detail"]


class TestAuditLoggerBatchLog:
    """Tests for batch logging capability."""

    def test_log_batch_writes_multiple_entries(self) -> None:
        """log_batch should write multiple log entries at once."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 3

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        entries = [
            {"action": "stitch", "entity_type": "encounter", "entity_id": "enc_001", "detail": "a"},
            {"action": "stitch", "entity_type": "encounter", "entity_id": "enc_002", "detail": "b"},
            {"action": "stitch", "entity_type": "encounter", "entity_id": "enc_003", "detail": "c"},
        ]
        logger.log_batch(entries)

        adapter.write_records.assert_called_once()
        records = adapter.write_records.call_args[0][1]
        assert len(records) == 3
        assert all("log_id" in r for r in records)
        assert all("timestamp" in r for r in records)
        assert all(r["run_id"] == "run_test" for r in records)


class TestAuditLoggerTableCreation:
    """Tests for audit log table DDL."""

    def test_ensure_table_creates_asre_audit_log(self) -> None:
        """AuditLogger.ensure_table() should create asre_audit_log table."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.write_records.return_value = 1

        logger = AuditLogger(adapter=adapter, run_id="run_test")
        logger.ensure_table()

        adapter.execute_ddl.assert_called_once()
        ddl = adapter.execute_ddl.call_args[0][0]
        assert "asre_audit_log" in ddl
        assert "CREATE TABLE IF NOT EXISTS" in ddl
        assert "log_id" in ddl
        assert "run_id" in ddl
        assert "timestamp" in ddl
        assert "action" in ddl
        assert "entity_type" in ddl
        assert "entity_id" in ddl
        assert "detail" in ddl


class TestAuditLoggerInPipeline:
    """Tests for AuditLogger integration with PipelineRunner."""

    def _make_runner_with_adapter(self, adapter: Any = None) -> PipelineRunner:
        if adapter is None:
            adapter = MagicMock()
            adapter.read_source.return_value = []
            adapter.write_records.return_value = 1
        config: dict[str, Any] = {"adapter": adapter}
        runner = PipelineRunner(config=config, mode="full")
        return runner

    def test_pipeline_context_has_audit_logger(self) -> None:
        """PipelineContext should carry an audit_logger when adapter is available."""
        from asre.pipeline.audit import AuditLogger

        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        runner = self._make_runner_with_adapter(adapter)

        class InspectorStage(PipelineStage):
            def __init__(self) -> None:
                from asre.observability.metrics import StageMetrics
                self.metrics: Any = StageMetrics("inspector", "")
                self.found_audit_logger = False

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                self.found_audit_logger = context.config.get("audit_logger") is not None
                return batch

        inspector = InspectorStage()
        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        stages: dict[str, PipelineStage] = {
            name: InspectorStage() for name in stage_names
        }
        runner._stages = stages
        runner.run()

        # At least one stage should have found the audit logger
        found = any(
            s.found_audit_logger  # type: ignore[attr-defined]
            for s in stages.values()
        )
        assert found, "PipelineContext should carry audit_logger"

    def test_audit_log_table_created_before_pipeline_run(self) -> None:
        """The asre_audit_log table should be created at the start of the pipeline run."""
        adapter = MagicMock()
        adapter.read_source.return_value = []
        adapter.write_records.return_value = 1

        runner = self._make_runner_with_adapter(adapter)

        class DummyStage(PipelineStage):
            def __init__(self, name: str) -> None:
                from asre.observability.metrics import StageMetrics
                self.metrics: Any = StageMetrics(name, "")

            def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
                return batch

        stage_names = [
            "ingest", "canonicalize", "facility_normalize",
            "stitch", "dedup", "reconcile", "score",
            "materialize", "quality_check",
        ]
        runner._stages = {name: DummyStage(name) for name in stage_names}
        runner.run()

        # Check that execute_ddl was called with asre_audit_log
        ddl_calls = [
            c[0][0] for c in adapter.execute_ddl.call_args_list
        ]
        audit_table_created = any("asre_audit_log" in ddl for ddl in ddl_calls)
        assert audit_table_created, "asre_audit_log table should be created during pipeline run"


class TestAuditLoggerInMaterializeStage:
    """Tests for audit logging in MaterializeStage."""

    def _make_event(
        self,
        event_id: str = "evt-001",
        event_type: str = "ADMIT",
        event_ts: datetime | None = None,
        source_system: str = "adt_vendor_x",
        source_record_id: str = "SRC-001",
    ) -> Any:
        from asre.models.canonical_event import CanonicalEvent

        now = datetime.now(tz=timezone.utc)
        return CanonicalEvent(
            event_id=event_id,
            patient_key="PAT-001",
            event_type=event_type,
            event_ts=event_ts or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system=source_system,
            source_record_id=source_record_id,
            facility_raw="St Marys",
            ingested_at=now,
            batch_id="batch-001",
            facility_canonical_id="FAC-001",
        )

    def _make_reconciled_encounter(
        self,
        encounter_id: str = "enc-abc123",
    ) -> Any:
        from asre.reconcile.reconciler import ReconciledClassification, ReconciledTimestamps
        from asre.reconcile.stage import ReconciledEncounter
        from asre.stitch.encounter_stitcher import StitchedEncounter

        events = [
            self._make_event(event_id="evt-001", event_type="ADMIT"),
            self._make_event(
                event_id="evt-002",
                event_type="DISCHARGE",
                event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
                source_record_id="SRC-002",
            ),
        ]
        enc = StitchedEncounter(
            patient_key="PAT-001",
            facility_canonical_id="FAC-001",
            events=events,
            encounter_type="inpatient",
            status="closed",
            has_discharge=True,
            obs_to_ip_conversion=False,
        )
        enc.encounter_id = encounter_id
        rec = ReconciledEncounter(enc)
        rec.reconciled_timestamps = ReconciledTimestamps(
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            admit_source_priority="adt",
            discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            discharge_source_priority="adt",
        )
        rec.reconciled_classification = ReconciledClassification(
            encounter_type="inpatient",
            drg="470",
            payer_id="PAYER-001",
            principal_diagnosis="J18.9",
            admitting_diagnosis="R06.0",
            diagnosis_codes=[{"code": "J18.9", "type": "ICD-10-CM", "sequence": 1, "poa": "Y"}],
        )
        rec.confidence_score = 0.85  # type: ignore[attr-defined]
        rec.confidence_flags = ["HAS_CLAIMS", "HAS_ADT_ADMIT"]
        return rec

    def test_materialize_logs_new_encounter_creation(self) -> None:
        """MaterializeStage should log audit entries for new encounters."""
        from asre.materialize.stage import MaterializeStage
        from asre.pipeline.audit import AUDIT_TABLE_NAME, AuditLogger

        adapter = MagicMock()
        adapter.execute_ddl = MagicMock()
        adapter.write_records = MagicMock(side_effect=lambda table, recs: len(recs))
        adapter.read_source = MagicMock(return_value=[])

        audit_logger = AuditLogger(adapter=adapter, run_id="run_test")

        context = PipelineContext(
            run_id="run_test",
            config={"adapter": adapter, "audit_logger": audit_logger},
            mode="full",
        )

        stage = MaterializeStage()
        stage.encounters_in = [self._make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_test", events=[])
        stage.run(batch, context)

        # Check that audit log entries were written
        audit_calls = [
            c for c in adapter.write_records.call_args_list
            if c[0][0] == AUDIT_TABLE_NAME
        ]
        assert len(audit_calls) > 0, "Audit log entries should be written for new encounters"
        records = audit_calls[0][0][1]
        assert any(r["action"] == "materialize" for r in records)
        assert any(r["entity_type"] == "encounter" for r in records)
        assert any("enc-abc123" in r["entity_id"] for r in records)

    def test_materialize_logs_encounter_update(self) -> None:
        """MaterializeStage should log audit entries for updated encounters."""
        from asre.materialize.stage import MaterializeStage
        from asre.pipeline.audit import AUDIT_TABLE_NAME, AuditLogger

        adapter = MagicMock()
        adapter.execute_ddl = MagicMock()
        adapter.write_records = MagicMock(side_effect=lambda table, recs: len(recs))
        adapter.read_source = MagicMock(return_value=[
            {"encounter_id": "enc-abc123", "created_at": "2024-01-01T00:00:00+00:00"}
        ])
        adapter._connection = MagicMock()

        audit_logger = AuditLogger(adapter=adapter, run_id="run_test")

        context = PipelineContext(
            run_id="run_test",
            config={"adapter": adapter, "audit_logger": audit_logger},
            mode="full",
        )

        stage = MaterializeStage()
        stage.encounters_in = [self._make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_test", events=[])
        stage.run(batch, context)

        # Check that audit log entries were written with "Updated"
        audit_calls = [
            c for c in adapter.write_records.call_args_list
            if c[0][0] == AUDIT_TABLE_NAME
        ]
        assert len(audit_calls) > 0, "Audit log entries should be written for updated encounters"
        records = audit_calls[0][0][1]
        assert any("Updated" in r.get("detail", "") or "updated" in r.get("detail", "").lower() for r in records)
