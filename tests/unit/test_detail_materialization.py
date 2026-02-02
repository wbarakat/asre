"""Tests for encounters detail materialization (US-073).

Verifies:
- Each event in an encounter gets a row in asre_encounters_detail
- role_in_encounter set per event: admit_anchor, discharge_anchor, supporting, duplicate
- Admit anchor: the event that provides admit_ts
- Discharge anchor: the event that provides discharge_ts
- Supporting: events that corroborate but don't anchor
- Duplicate: events marked as duplicates in dedup stage
- Integration: verify detail rows match encounter events
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from asre.materialize.stage import (
    DETAIL_TABLE_NAME,
    MaterializeStage,
    assign_event_roles,
    event_to_detail_record,
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
    role_in_encounter: str | None = None,
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
        role_in_encounter=role_in_encounter,
    )


def _make_reconciled_encounter(
    encounter_id: str = "enc-abc123",
    patient_key: str = "PAT-001",
    events: list[CanonicalEvent] | None = None,
    admit_ts: datetime | None = None,
    discharge_ts: datetime | None = None,
    admit_source_priority: str = "adt",
    discharge_source_priority: str | None = "adt",
) -> ReconciledEncounter:
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
        facility_canonical_id="FAC-001",
        events=events,
        encounter_type="inpatient",
        status="closed",
        has_discharge=True,
    )
    enc.encounter_id = encounter_id
    rec = ReconciledEncounter(enc)
    rec.reconciled_timestamps = ReconciledTimestamps(
        admit_ts=admit_ts or datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        admit_source_priority=admit_source_priority,
        discharge_ts=discharge_ts or datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        discharge_source_priority=discharge_source_priority,
    )
    rec.reconciled_classification = ReconciledClassification(
        encounter_type="inpatient",
        drg="470",
        payer_id="PAYER-001",
        principal_diagnosis="J18.9",
        admitting_diagnosis="R06.0",
        diagnosis_codes=[],
    )
    rec.confidence_score = 0.85  # type: ignore[attr-defined]
    rec.confidence_flags = ["HAS_ADT_ADMIT"]
    return rec


class TestAssignEventRoles:
    """Tests for the assign_event_roles function."""

    def test_admit_anchor_assigned(self) -> None:
        """The event providing admit_ts should get role=admit_anchor."""
        admit_event = _make_event(
            event_id="evt-admit",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        discharge_event = _make_event(
            event_id="evt-discharge",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_record_id="SRC-002",
        )
        enc = _make_reconciled_encounter(
            events=[admit_event, discharge_event],
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        )

        assign_event_roles(enc)

        assert admit_event.role_in_encounter == "admit_anchor"

    def test_discharge_anchor_assigned(self) -> None:
        """The event providing discharge_ts should get role=discharge_anchor."""
        admit_event = _make_event(
            event_id="evt-admit",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        discharge_event = _make_event(
            event_id="evt-discharge",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_record_id="SRC-002",
        )
        enc = _make_reconciled_encounter(
            events=[admit_event, discharge_event],
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        )

        assign_event_roles(enc)

        assert discharge_event.role_in_encounter == "discharge_anchor"

    def test_supporting_events(self) -> None:
        """Events that are not anchors or duplicates should get role=supporting."""
        admit_event = _make_event(
            event_id="evt-admit",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        transfer_event = _make_event(
            event_id="evt-transfer",
            event_type="TRANSFER_IN",
            event_ts=datetime(2024, 1, 16, 8, 0, tzinfo=timezone.utc),
            source_record_id="SRC-003",
        )
        discharge_event = _make_event(
            event_id="evt-discharge",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_record_id="SRC-002",
        )
        enc = _make_reconciled_encounter(
            events=[admit_event, transfer_event, discharge_event],
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        )

        assign_event_roles(enc)

        assert transfer_event.role_in_encounter == "supporting"

    def test_duplicate_events_preserved(self) -> None:
        """Events already marked as duplicate should keep that role."""
        admit_event = _make_event(
            event_id="evt-admit",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
        )
        dup_event = _make_event(
            event_id="evt-dup",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 15, tzinfo=timezone.utc),
            source_record_id="SRC-DUP",
            role_in_encounter="duplicate",
        )
        discharge_event = _make_event(
            event_id="evt-discharge",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_record_id="SRC-002",
        )
        enc = _make_reconciled_encounter(
            events=[admit_event, dup_event, discharge_event],
            admit_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        )

        assign_event_roles(enc)

        assert dup_event.role_in_encounter == "duplicate"
        assert admit_event.role_in_encounter == "admit_anchor"
        assert discharge_event.role_in_encounter == "discharge_anchor"

    def test_claims_admit_anchor_by_source_priority(self) -> None:
        """When reconciled admit comes from claims, the matching claims event is admit_anchor."""
        adt_admit = _make_event(
            event_id="evt-adt-admit",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
        )
        claims_admit = _make_event(
            event_id="evt-claims-admit",
            event_type="CLAIM_ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            source_system="claims_ch",
            source_record_id="SRC-CLAIMS",
        )
        discharge_event = _make_event(
            event_id="evt-discharge",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_record_id="SRC-002",
        )
        enc = _make_reconciled_encounter(
            events=[adt_admit, claims_admit, discharge_event],
            # Reconciled admit_ts comes from claims
            admit_ts=datetime(2024, 1, 15, 10, 30, tzinfo=timezone.utc),
            admit_source_priority="claims",
            discharge_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
        )

        assign_event_roles(enc)

        assert claims_admit.role_in_encounter == "admit_anchor"
        assert adt_admit.role_in_encounter == "supporting"

    def test_no_reconciled_timestamps_all_supporting(self) -> None:
        """When no reconciled timestamps, all non-duplicate events are supporting."""
        admit_event = _make_event(event_id="evt-1", event_type="ADMIT")
        discharge_event = _make_event(
            event_id="evt-2",
            event_type="DISCHARGE",
            event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
            source_record_id="SRC-002",
        )
        enc = _make_reconciled_encounter(events=[admit_event, discharge_event])
        enc.reconciled_timestamps = None

        assign_event_roles(enc)

        assert admit_event.role_in_encounter == "supporting"
        assert discharge_event.role_in_encounter == "supporting"


class TestEventToDetailRecord:
    """Tests for the event_to_detail_record conversion function."""

    def test_detail_record_fields(self) -> None:
        """Detail record should contain encounter_id, event_id, event_type, event_ts, source_system, role_in_encounter."""
        event = _make_event(
            event_id="evt-001",
            event_type="ADMIT",
            event_ts=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            source_system="adt_vendor_x",
            role_in_encounter="admit_anchor",
        )
        record = event_to_detail_record(event, "enc-abc123")

        assert record["encounter_id"] == "enc-abc123"
        assert record["event_id"] == "evt-001"
        assert record["event_type"] == "ADMIT"
        assert record["event_ts"] == "2024-01-15T10:00:00+00:00"
        assert record["source_system"] == "adt_vendor_x"
        assert record["role_in_encounter"] == "admit_anchor"

    def test_detail_record_duplicate_role(self) -> None:
        """Duplicate events should have role=duplicate in detail record."""
        event = _make_event(
            event_id="evt-dup",
            event_type="ADMIT",
            role_in_encounter="duplicate",
        )
        record = event_to_detail_record(event, "enc-abc123")
        assert record["role_in_encounter"] == "duplicate"


class TestMaterializeStageDetail:
    """Tests for MaterializeStage encounters detail materialization."""

    def _make_context(self, adapter: Any = None) -> PipelineContext:
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

    def test_detail_rows_written_for_each_event(self) -> None:
        """Each event in an encounter gets a row in asre_encounters_detail."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        enc = _make_reconciled_encounter()  # Has 2 events

        stage = MaterializeStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        # write_records should be called for both the main table and detail table
        write_calls = adapter.write_records.call_args_list
        detail_calls = [c for c in write_calls if c[0][0] == DETAIL_TABLE_NAME]
        assert len(detail_calls) == 1
        detail_records = detail_calls[0][0][1]
        assert len(detail_records) == 2  # 2 events -> 2 detail rows

    def test_detail_roles_assigned_correctly(self) -> None:
        """Detail rows have correct role_in_encounter values."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        enc = _make_reconciled_encounter()

        stage = MaterializeStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        write_calls = adapter.write_records.call_args_list
        detail_calls = [c for c in write_calls if c[0][0] == DETAIL_TABLE_NAME]
        detail_records = detail_calls[0][0][1]

        roles = {r["event_id"]: r["role_in_encounter"] for r in detail_records}
        assert roles["evt-001"] == "admit_anchor"
        assert roles["evt-002"] == "discharge_anchor"

    def test_detail_table_created(self) -> None:
        """asre_encounters_detail table should be created if it doesn't exist."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        ddl_calls = adapter.execute_ddl.call_args_list
        ddl_strs = [c[0][0] for c in ddl_calls]
        detail_ddl = [d for d in ddl_strs if DETAIL_TABLE_NAME in d]
        assert len(detail_ddl) == 1
        assert "CREATE TABLE IF NOT EXISTS" in detail_ddl[0]

    def test_multiple_encounters_detail_rows(self) -> None:
        """Multiple encounters should produce detail rows for all events."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        enc1 = _make_reconciled_encounter(encounter_id="enc-001")
        enc2 = _make_reconciled_encounter(
            encounter_id="enc-002",
            patient_key="PAT-002",
            events=[
                _make_event(
                    event_id="evt-003",
                    event_type="ADMIT",
                    patient_key="PAT-002",
                ),
                _make_event(
                    event_id="evt-004",
                    event_type="TRANSFER_IN",
                    patient_key="PAT-002",
                    event_ts=datetime(2024, 1, 16, 8, 0, tzinfo=timezone.utc),
                    source_record_id="SRC-003",
                ),
                _make_event(
                    event_id="evt-005",
                    event_type="DISCHARGE",
                    patient_key="PAT-002",
                    event_ts=datetime(2024, 1, 18, 14, 0, tzinfo=timezone.utc),
                    source_record_id="SRC-004",
                ),
            ],
        )

        stage = MaterializeStage()
        stage.encounters_in = [enc1, enc2]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        write_calls = adapter.write_records.call_args_list
        detail_calls = [c for c in write_calls if c[0][0] == DETAIL_TABLE_NAME]
        assert len(detail_calls) == 1
        detail_records = detail_calls[0][0][1]
        # enc1 has 2 events, enc2 has 3 events = 5 total
        assert len(detail_records) == 5

    def test_detail_metrics_tracked(self) -> None:
        """Detail materialization count should be tracked."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        enc = _make_reconciled_encounter()  # 2 events

        stage = MaterializeStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.detail_rows_written == 2

    def test_no_detail_rows_when_no_adapter(self) -> None:
        """When no adapter, detail rows should not be written."""
        context = self._make_context(adapter=None)

        stage = MaterializeStage()
        stage.encounters_in = [_make_reconciled_encounter()]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        assert stage.detail_rows_written == 0

    def test_detail_encounter_id_matches(self) -> None:
        """Each detail row's encounter_id should match the encounter it belongs to."""
        adapter = self._make_adapter()
        context = self._make_context(adapter=adapter)

        enc = _make_reconciled_encounter(encounter_id="enc-specific-id")

        stage = MaterializeStage()
        stage.encounters_in = [enc]

        batch = EventBatch(batch_id="run_001", events=[])
        stage.run(batch, context)

        write_calls = adapter.write_records.call_args_list
        detail_calls = [c for c in write_calls if c[0][0] == DETAIL_TABLE_NAME]
        detail_records = detail_calls[0][0][1]
        for row in detail_records:
            assert row["encounter_id"] == "enc-specific-id"
