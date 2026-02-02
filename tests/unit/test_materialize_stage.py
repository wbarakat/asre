"""Tests for MaterializeStage (US-072).

Verifies:
- encounter_to_record converts ReconciledEncounter to a flat dict
- MaterializeStage inserts new encounters (created_at set)
- MaterializeStage updates existing encounters (updated_at set, created_at preserved)
- All fields from SPEC §3.4 admission_events_unified populated
- asre_version set to current engine version
- Integration: materialize encounters, verify table contents
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from asre.materialize.stage import (
    ASRE_VERSION,
    TABLE_NAME,
    MaterializeStage,
    encounter_to_record,
)
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext
from asre.reconcile.reconciler import (
    ReconciledClassification,
    ReconciledTimestamps,
)
from asre.reconcile.stage import ReconciledEncounter
from asre.stitch.encounter_stitcher import StitchedEncounter


def _make_event(
    event_id: str = "evt-001",
    patient_key: str = "PAT-001",
    event_type: str = "ADMIT",
    event_ts: datetime | None = None,
    source_system: str = "adt_vendor_x",
    source_record_id: str = "SRC-001",
    facility_raw: str = "St Marys",
    facility_canonical_id: str | None = "FAC-001",
) -> CanonicalEvent:
    now = datetime.now(tz=timezone.utc)
    return CanonicalEvent(
        event_id=event_id,
        patient_key=patient_key,
        event_type=event_type,
        event_ts=event_ts or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        source_system=source_system,
        source_record_id=source_record_id,
        facility_raw=facility_raw,
        ingested_at=now,
        batch_id="batch-001",
        facility_canonical_id=facility_canonical_id,
    )


def _make_stitched_encounter(
    patient_key: str = "PAT-001",
    facility_canonical_id: str = "FAC-001",
    encounter_id: str = "enc-abc123",
    events: list[CanonicalEvent] | None = None,
    encounter_type: str = "inpatient",
    status: str = "closed",
    has_discharge: bool = True,
    obs_to_ip_conversion: bool = False,
) -> StitchedEncounter:
    if events is None:
        events = [
            _make_event(
                event_id="evt-001",
                event_type="ADMIT",
                event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
                source_system="adt_vendor_x",
            ),
            _make_event(
                event_id="evt-002",
                event_type="DISCHARGE",
                event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
                source_system="adt_vendor_x",
                source_record_id="SRC-002",
            ),
        ]
    enc = StitchedEncounter(
        patient_key=patient_key,
        facility_canonical_id=facility_canonical_id,
        events=events,
        encounter_type=encounter_type,
        status=status,
        has_discharge=has_discharge,
        obs_to_ip_conversion=obs_to_ip_conversion,
    )
    enc.encounter_id = encounter_id
    return enc


def _make_reconciled_encounter(
    **kwargs: Any,
) -> ReconciledEncounter:
    stitched = _make_stitched_encounter(**kwargs)
    rec = ReconciledEncounter(stitched)
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


class TestEncounterToRecord:
    """Tests for the encounter_to_record conversion function."""

    def test_all_fields_populated(self) -> None:
        """All fields from SPEC §3.4 are present in the output record."""
        enc = _make_reconciled_encounter()
        now = datetime(2024, 2, 1, 12, 0, tzinfo=timezone.utc)
        record = encounter_to_record(enc, now, "run_001")

        expected_fields = {
            "encounter_id", "patient_key", "encounter_type", "status",
            "admit_ts", "discharge_ts", "los_hours",
            "facility_canonical_id", "facility_name", "is_acute",
            "source_event_ids", "source_systems",
            "has_adt", "has_claims", "has_auth",
            "confidence_score", "confidence_flags",
            "admit_source_priority", "discharge_source_priority",
            "payer_id", "drg", "principal_diagnosis", "admitting_diagnosis",
            "diagnosis_codes", "is_readmission", "readmission_days",
            "obs_to_ip_conversion", "transfer_chain", "episode_id",
            "created_at", "updated_at", "asre_version",
        }
        assert set(record.keys()) == expected_fields

    def test_encounter_id(self) -> None:
        enc = _make_reconciled_encounter(encounter_id="enc-xyz")
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["encounter_id"] == "enc-xyz"

    def test_reconciled_timestamps_used(self) -> None:
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["admit_ts"] == "2024-01-15T10:00:00+00:00"
        assert record["discharge_ts"] == "2024-01-18T14:00:00+00:00"
        assert record["admit_source_priority"] == "adt"
        assert record["discharge_source_priority"] == "adt"

    def test_los_hours_computed(self) -> None:
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        # 3 days + 4 hours = 76 hours
        assert record["los_hours"] == pytest.approx(76.0)

    def test_los_hours_none_when_no_discharge(self) -> None:
        enc = _make_reconciled_encounter(status="open", has_discharge=False)
        enc.reconciled_timestamps = ReconciledTimestamps(
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            admit_source_priority="adt",
            discharge_ts=None,
            discharge_source_priority=None,
        )
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["los_hours"] is None
        assert record["discharge_ts"] is None

    def test_reconciled_classification_used(self) -> None:
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["encounter_type"] == "inpatient"
        assert record["drg"] == "470"
        assert record["payer_id"] == "PAYER-001"
        assert record["principal_diagnosis"] == "J18.9"
        assert record["admitting_diagnosis"] == "R06.0"
        diag = json.loads(record["diagnosis_codes"])
        assert len(diag) == 1
        assert diag[0]["code"] == "J18.9"

    def test_source_info(self) -> None:
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        event_ids = json.loads(record["source_event_ids"])
        assert "evt-001" in event_ids
        assert "evt-002" in event_ids
        assert record["has_adt"] is True
        assert record["has_claims"] is False
        assert record["has_auth"] is False

    def test_source_info_mixed(self) -> None:
        events = [
            _make_event(event_id="evt-1", source_system="adt_vendor_x", event_type="ADMIT"),
            _make_event(event_id="evt-2", source_system="claims_ch", event_type="CLAIM_DISCHARGE",
                        event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
                        source_record_id="SRC-002"),
        ]
        enc = _make_reconciled_encounter(events=events)
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["has_adt"] is True
        assert record["has_claims"] is True
        assert record["has_auth"] is False

    def test_confidence_fields(self) -> None:
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["confidence_score"] == 0.85
        flags = json.loads(record["confidence_flags"])
        assert "HAS_CLAIMS" in flags
        assert "HAS_ADT_ADMIT" in flags

    def test_asre_version_set(self) -> None:
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["asre_version"] == ASRE_VERSION

    def test_obs_to_ip_conversion(self) -> None:
        enc = _make_reconciled_encounter(obs_to_ip_conversion=True)
        record = encounter_to_record(enc, datetime.now(tz=timezone.utc), "run_001")
        assert record["obs_to_ip_conversion"] is True

    def test_created_at_and_updated_at_set(self) -> None:
        now = datetime(2024, 2, 1, 12, 0, tzinfo=timezone.utc)
        enc = _make_reconciled_encounter()
        record = encounter_to_record(enc, now, "run_001")
        assert record["created_at"] == "2024-02-01T12:00:00+00:00"
        assert record["updated_at"] == "2024-02-01T12:00:00+00:00"


class TestMaterializeStage:
    """Tests for the MaterializeStage pipeline stage."""

    def _make_context(
        self,
        adapter: Any = None,
    ) -> PipelineContext:
        config: dict[str, Any] = {}
        if adapter is not None:
            config["adapter"] = adapter
        return PipelineContext(
            run_id="run_20240201_120000",
            config=config,
            mode="full",
        )

    def _make_adapter(
        self,
        existing_ids: dict[str, str] | None = None,
    ) -> MagicMock:
        adapter = MagicMock()
        adapter.execute_ddl = MagicMock()
        adapter.write_records = MagicMock(side_effect=lambda table, recs: len(recs))

        # read_source returns existing encounter_ids
        if existing_ids:
            adapter.read_source = MagicMock(
                return_value=[
                    {"encounter_id": eid, "created_at": cat}
                    for eid, cat in existing_ids.items()
                ]
            )
        else:
            adapter.read_source = MagicMock(return_value=[])

        return adapter

    def test_insert_new_encounters(self) -> None:
        """New encounters should be inserted with created_at set."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.encounters_materialized == 1
        assert stage.encounters_inserted == 1
        assert stage.encounters_updated == 0

        # write_records was called with the table name
        adapter.write_records.assert_called_once()
        call_args = adapter.write_records.call_args
        assert call_args[0][0] == TABLE_NAME
        records = call_args[0][1]
        assert len(records) == 1
        assert records[0]["encounter_id"] == "enc-abc123"
        assert records[0]["created_at"] is not None

    def test_update_existing_encounter(self) -> None:
        """Existing encounters should be updated, preserving original created_at."""
        original_created_at = "2024-01-01T00:00:00+00:00"
        adapter = self._make_adapter(
            existing_ids={"enc-abc123": original_created_at}
        )
        # Add mock _connection for DELETE in upsert
        mock_conn = MagicMock()
        adapter._connection = mock_conn

        context = self._make_context(adapter=adapter)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.encounters_materialized == 1
        assert stage.encounters_inserted == 0
        assert stage.encounters_updated == 1

        # write_records called for updates
        call_args = adapter.write_records.call_args
        records = call_args[0][1]
        assert records[0]["created_at"] == original_created_at

    def test_no_adapter_skips_materialization(self) -> None:
        """When no adapter is configured, skip materialization."""
        context = self._make_context(adapter=None)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.encounters_materialized == 0

    def test_multiple_encounters(self) -> None:
        """Multiple encounters are materialized correctly."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        enc1 = _make_reconciled_encounter(encounter_id="enc-001")
        enc2 = _make_reconciled_encounter(encounter_id="enc-002", patient_key="PAT-002")

        stage = MaterializeStage()
        stage.encounters_in = [enc1, enc2]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.encounters_materialized == 2
        assert stage.encounters_inserted == 2

    def test_mixed_insert_and_update(self) -> None:
        """Mix of new and existing encounters."""
        adapter = self._make_adapter(
            existing_ids={"enc-001": "2024-01-01T00:00:00+00:00"}
        )
        mock_conn = MagicMock()
        adapter._connection = mock_conn

        context = self._make_context(adapter=adapter)

        enc1 = _make_reconciled_encounter(encounter_id="enc-001")
        enc2 = _make_reconciled_encounter(encounter_id="enc-002", patient_key="PAT-002")

        stage = MaterializeStage()
        stage.encounters_in = [enc1, enc2]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.encounters_inserted == 1
        assert stage.encounters_updated == 1
        assert stage.encounters_materialized == 2

    def test_ensure_table_called(self) -> None:
        """_ensure_table should be called to create the table if needed."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        # execute_ddl called with CREATE TABLE IF NOT EXISTS
        adapter.execute_ddl.assert_called_once()
        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS" in ddl
        assert TABLE_NAME in ddl

    def test_metrics_tracked(self) -> None:
        """Stage metrics should be populated after run."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        metrics = stage.metrics.to_dict()
        assert metrics["records_in"] == 1
        assert metrics["records_out"] == 1
        assert metrics["stage_name"] == "materialize"
        assert metrics["status"] == "success"

    def test_empty_encounters(self) -> None:
        """Zero encounters produces zero materialized."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        stage = MaterializeStage()
        stage.encounters_in = []

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.encounters_materialized == 0
        assert stage.metrics.records_in == 0
        assert stage.metrics.records_out == 0
