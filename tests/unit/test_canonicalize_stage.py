"""Tests for CanonicalizeStage - pipeline stage composing all canonicalization logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from asre.models.batch import EventBatch
from asre.pipeline.runner import PipelineContext


def _make_context(
    sources: list[dict[str, Any]],
    raw_records: list[dict[str, Any]],
    run_id: str = "test-run-001",
) -> PipelineContext:
    """Build a PipelineContext with sources and raw_records in config."""
    return PipelineContext(
        run_id=run_id,
        config={
            "sources": sources,
            "raw_records": raw_records,
        },
        mode="full",
    )


def _adt_source_config() -> dict[str, Any]:
    """Minimal ADT source config for testing."""
    return {
        "name": "adt_vendor_x",
        "type": "adt",
        "source": {"table": "raw_adt", "incremental_key": "updated_at"},
        "field_mappings": {
            "patient_key": "patient_id",
            "event_ts": "event_timestamp",
            "source_record_id": "msg_id",
            "facility_raw": "facility_name",
            "patient_class": "patient_class",
        },
        "event_type_rules": {
            "source_field": "hl7_event",
            "mappings": {
                "A01": "ADMIT",
                "A03": "DISCHARGE",
                "A02": "TRANSFER_IN",
            },
            "conditional_mappings": [
                {
                    "when": "hl7_event == 'A01' AND patient_class == 'ED'",
                    "event_type": "ED_ARRIVAL",
                },
            ],
            "admit_flag_expression": "event_type IN ('ADMIT', 'ED_ARRIVAL')",
            "discharge_flag_expression": "event_type IN ('DISCHARGE', 'ED_DEPARTURE')",
        },
    }


def _claims_source_config() -> dict[str, Any]:
    """Minimal claims source config for testing."""
    return {
        "name": "claims_clearinghouse",
        "type": "claims",
        "source": {"table": "raw_claims", "incremental_key": "updated_at"},
        "field_mappings": {
            "patient_key": "member_id",
            "event_ts": "admission_date",
            "source_record_id": "claim_id",
            "facility_raw": "facility_name",
            "payer_id": "payer",
            "drg": "drg_code",
            "principal_diagnosis": "primary_dx",
            "diagnosis_codes": "dx_codes",
        },
        "event_type_rules": {
            "source_field": "claim_type",
            "mappings": {"IP": "CLAIM_ADMIT"},
        },
        "paired_events": {
            "admit": {"event_ts": "admission_date", "event_type": "CLAIM_ADMIT"},
            "discharge": {"event_ts": "discharge_date", "event_type": "CLAIM_DISCHARGE"},
        },
        "patient_class_rules": {
            "conditions": [
                {"when": "bill_type_code LIKE '11%'", "patient_class": "inpatient"},
                {"when": "bill_type_code LIKE '13%'", "patient_class": "outpatient"},
            ],
        },
    }


def _auth_source_config() -> dict[str, Any]:
    """Minimal auth source config for testing."""
    return {
        "name": "auth_portal",
        "type": "auth",
        "source": {"table": "raw_auth", "incremental_key": "updated_at"},
        "field_mappings": {
            "patient_key": "member_id",
            "event_ts": "auth_date",
            "source_record_id": "auth_id",
            "facility_raw": "facility_name",
        },
        "event_type_rules": {
            "source_field": "auth_type",
            "mappings": {"INPATIENT": "AUTH_REQUESTED"},
        },
        "auth_status_map": {
            "source_field": "auth_status",
            "mappings": {
                "A": "approved",
                "D": "denied",
                "P": "pending",
            },
        },
    }


def _make_adt_record(
    patient_id: str = "PAT001",
    hl7_event: str = "A01",
    patient_class: str = "IP",
    msg_id: str = "MSG001",
    facility: str = "General Hospital",
    event_ts: str = "2024-01-15T10:00:00",
) -> dict[str, Any]:
    """Build a raw ADT record dict (as IngestStage would annotate it)."""
    base: dict[str, Any] = {
        "patient_id": patient_id,
        "hl7_event": hl7_event,
        "patient_class": patient_class,
        "msg_id": msg_id,
        "facility_name": facility,
        "event_timestamp": event_ts,
    }
    return {
        **base,
        "_raw_payload": dict(base),
        "_source_name": "adt_vendor_x",
        "_source_type": "adt",
    }


def _make_claims_record(
    member_id: str = "PAT001",
    claim_id: str = "CLM001",
    facility: str = "General Hospital",
    admission_date: str = "2024-01-15T08:00:00",
    discharge_date: str = "2024-01-18T14:00:00",
    bill_type_code: str = "111",
    payer: str = "BCBS",
    drg_code: str = "470",
    primary_dx: str = "J18.9",
    dx_codes: str = '["J18.9", "R06.0"]',
) -> dict[str, Any]:
    """Build a raw claims record dict."""
    base: dict[str, Any] = {
        "member_id": member_id,
        "claim_id": claim_id,
        "facility_name": facility,
        "admission_date": admission_date,
        "discharge_date": discharge_date,
        "bill_type_code": bill_type_code,
        "claim_type": "IP",
        "payer": payer,
        "drg_code": drg_code,
        "primary_dx": primary_dx,
        "dx_codes": dx_codes,
    }
    return {
        **base,
        "_raw_payload": dict(base),
        "_source_name": "claims_clearinghouse",
        "_source_type": "claims",
    }


def _make_auth_record(
    member_id: str = "PAT001",
    auth_id: str = "AUTH001",
    facility: str = "General Hospital",
    auth_date: str = "2024-01-14T12:00:00",
    auth_status: str = "A",
) -> dict[str, Any]:
    """Build a raw auth record dict."""
    base: dict[str, Any] = {
        "member_id": member_id,
        "auth_id": auth_id,
        "facility_name": facility,
        "auth_date": auth_date,
        "auth_status": auth_status,
        "auth_type": "INPATIENT",
    }
    return {
        **base,
        "_raw_payload": dict(base),
        "_source_name": "auth_portal",
        "_source_type": "auth",
    }


# ── Test: Interface ─────────────────────────────────────────────


class TestCanonicalizeStageInterface:
    """Verify CanonicalizeStage implements PipelineStage."""

    def test_implements_pipeline_stage(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage
        from asre.pipeline.runner import PipelineStage

        stage = CanonicalizeStage()
        assert isinstance(stage, PipelineStage)

    def test_has_run_method(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        assert callable(getattr(stage, "run", None))

    def test_has_metrics(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        assert hasattr(stage, "metrics")


# ── Test: ADT records ────────────────────────────────────────────


class TestCanonicalizeADT:
    """Verify ADT record canonicalization."""

    def test_adt_record_produces_one_event(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record()]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert len(result.events) == 1

    def test_adt_event_type_resolved(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record(hl7_event="A01", patient_class="IP")]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].event_type == "ADMIT"

    def test_adt_admit_flag_set(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record(hl7_event="A01", patient_class="IP")]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].admit_flag is True

    def test_adt_discharge_event(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record(hl7_event="A03", msg_id="MSG002")]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].event_type == "DISCHARGE"
        assert result.events[0].discharge_flag is True

    def test_adt_conditional_mapping_ed(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record(hl7_event="A01", patient_class="ED")]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].event_type == "ED_ARRIVAL"
        assert result.events[0].admit_flag is True

    def test_adt_patient_key_mapped(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record(patient_id="PAT-999")]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].patient_key == "PAT-999"

    def test_adt_source_system(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record()]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].source_system == "adt_vendor_x"


# ── Test: Claims records ─────────────────────────────────────────


class TestCanonicalizeClaims:
    """Verify claims record canonicalization with paired event emission."""

    def test_claims_record_produces_two_events(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record()]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert len(result.events) == 2

    def test_claims_admit_event(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record()]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)
        admit_event = result.events[0]

        assert admit_event.event_type == "CLAIM_ADMIT"
        assert admit_event.admit_flag is True

    def test_claims_discharge_event(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record()]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)
        discharge_event = result.events[1]

        assert discharge_event.event_type == "CLAIM_DISCHARGE"
        assert discharge_event.discharge_flag is True

    def test_claims_patient_class_resolved(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record(bill_type_code="111")]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        # Both paired events should have patient_class set
        assert result.events[0].patient_class == "inpatient"
        assert result.events[1].patient_class == "inpatient"

    def test_claims_diagnosis_mapped(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record(primary_dx="J18.9", dx_codes='["J18.9", "R06.0"]')]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        # Diagnosis should be mapped on paired events
        assert result.events[0].principal_diagnosis == "J18.9"
        assert result.events[0].diagnosis_codes is not None
        assert len(result.events[0].diagnosis_codes) == 2

    def test_claims_unique_event_ids(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record()]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].event_id != result.events[1].event_id


# ── Test: Auth records ───────────────────────────────────────────


class TestCanonicalizeAuth:
    """Verify auth record canonicalization."""

    def test_auth_record_produces_one_event(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_auth_record()]
        ctx = _make_context([_auth_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert len(result.events) == 1

    def test_auth_flag_set(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_auth_record(auth_status="A")]
        ctx = _make_context([_auth_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].auth_flag is True

    def test_auth_status_mapped(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_auth_record(auth_status="A")]
        ctx = _make_context([_auth_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].auth_status == "approved"

    def test_auth_event_type_derived(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_auth_record(auth_status="A")]
        ctx = _make_context([_auth_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].event_type == "AUTH_APPROVED"

    def test_auth_denied_event_type(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_auth_record(auth_status="D")]
        ctx = _make_context([_auth_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert result.events[0].event_type == "AUTH_DENIED"
        assert result.events[0].auth_status == "denied"


# ── Test: Mixed batch ────────────────────────────────────────────


class TestCanonicalizeMixedBatch:
    """Verify mixed batch of ADT + claims + auth records."""

    def test_mixed_batch_correct_total(self) -> None:
        """ADT(1 event) + claims(2 events) + auth(1 event) = 4 events."""
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [
            _make_adt_record(),
            _make_claims_record(),
            _make_auth_record(),
        ]
        sources = [_adt_source_config(), _claims_source_config(), _auth_source_config()]
        ctx = _make_context(sources, records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        # 1 ADT + 2 claims (paired) + 1 auth = 4
        assert len(result.events) == 4

    def test_mixed_batch_event_types(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [
            _make_adt_record(hl7_event="A01", patient_class="IP"),
            _make_claims_record(),
            _make_auth_record(auth_status="A"),
        ]
        sources = [_adt_source_config(), _claims_source_config(), _auth_source_config()]
        ctx = _make_context(sources, records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        event_types = [e.event_type for e in result.events]
        assert "ADMIT" in event_types
        assert "CLAIM_ADMIT" in event_types
        assert "CLAIM_DISCHARGE" in event_types
        assert "AUTH_APPROVED" in event_types

    def test_mixed_batch_all_have_batch_id(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [
            _make_adt_record(),
            _make_claims_record(),
            _make_auth_record(),
        ]
        sources = [_adt_source_config(), _claims_source_config(), _auth_source_config()]
        ctx = _make_context(sources, records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        for event in result.events:
            assert event.batch_id == "batch-001"


# ── Test: Error tolerance ────────────────────────────────────────


class TestCanonicalizeErrorTolerance:
    """Verify error tolerance: bad records skipped, good records processed."""

    def test_invalid_records_skipped(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        good_record = _make_adt_record()
        bad_record: dict[str, Any] = {
            "patient_id": None,  # Missing patient_key
            "hl7_event": "A01",
            "msg_id": "BAD001",
            "event_timestamp": "2024-01-15T10:00:00",
            "_raw_payload": {},
            "_source_name": "adt_vendor_x",
            "_source_type": "adt",
        }
        records = [good_record, bad_record]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert len(result.events) == 1

    def test_error_count_in_metrics(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        good_record = _make_adt_record()
        bad1: dict[str, Any] = {
            "patient_id": None,
            "hl7_event": "A01",
            "msg_id": "BAD001",
            "event_timestamp": "2024-01-15T10:00:00",
            "_raw_payload": {},
            "_source_name": "adt_vendor_x",
            "_source_type": "adt",
        }
        bad2: dict[str, Any] = {
            "patient_id": "PAT002",
            "hl7_event": "A01",
            "msg_id": "BAD002",
            "event_timestamp": None,  # Missing event_ts
            "_raw_payload": {},
            "_source_name": "adt_vendor_x",
            "_source_type": "adt",
        }
        records = [good_record, bad1, bad2]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        stage.run(batch, ctx)

        assert stage.metrics.errors == 2

    def test_batch_with_all_invalid_produces_empty(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        bad_record: dict[str, Any] = {
            "patient_id": None,
            "hl7_event": "A01",
            "msg_id": "BAD001",
            "event_timestamp": None,
            "_raw_payload": {},
            "_source_name": "adt_vendor_x",
            "_source_type": "adt",
        }
        records = [bad_record]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert len(result.events) == 0
        assert stage.metrics.errors == 1


# ── Test: Metrics tracking ───────────────────────────────────────


class TestCanonicalizeMetrics:
    """Verify stage metrics are tracked correctly."""

    def test_records_in_count(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record(msg_id=f"MSG{i}") for i in range(5)]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        stage.run(batch, ctx)

        assert stage.metrics.records_in == 5

    def test_records_out_includes_paired_expansion(self) -> None:
        """Claims paired event expansion means records_out > records_in."""
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_claims_record()]
        ctx = _make_context([_claims_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        stage.run(batch, ctx)

        assert stage.metrics.records_in == 1
        assert stage.metrics.records_out == 2  # Paired expansion

    def test_metrics_stage_name(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record()]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        stage.run(batch, ctx)

        assert stage.metrics.stage_name == "canonicalize"

    def test_metrics_status_success(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        records = [_make_adt_record()]
        ctx = _make_context([_adt_source_config()], records)
        batch = EventBatch(batch_id="batch-001", events=[])

        stage.run(batch, ctx)

        assert stage.metrics.status == "success"

    def test_empty_input_produces_empty_output(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        ctx = _make_context([_adt_source_config()], [])
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        assert len(result.events) == 0
        assert stage.metrics.records_in == 0
        assert stage.metrics.records_out == 0


# ── Test: Source routing ─────────────────────────────────────────


class TestCanonicalizeSourceRouting:
    """Verify records are routed to correct canonicalization logic by source type."""

    def test_unknown_source_type_skipped(self) -> None:
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        record: dict[str, Any] = {
            "patient_id": "PAT001",
            "event_timestamp": "2024-01-15T10:00:00",
            "msg_id": "MSG001",
            "_raw_payload": {},
            "_source_name": "unknown_source",
            "_source_type": "unknown",
        }
        # Provide a source config but records have mismatching source_name
        ctx = _make_context([_adt_source_config()], [record])
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        # Unknown source_name has no matching config, should be skipped
        assert len(result.events) == 0

    def test_records_matched_to_correct_source_config(self) -> None:
        """Each record's _source_name must match a source config name."""
        from asre.canonicalize.stage import CanonicalizeStage

        stage = CanonicalizeStage()
        adt_record = _make_adt_record()
        claims_record = _make_claims_record()
        sources = [_adt_source_config(), _claims_source_config()]
        ctx = _make_context(sources, [adt_record, claims_record])
        batch = EventBatch(batch_id="batch-001", events=[])

        result = stage.run(batch, ctx)

        # ADT produces 1, claims produces 2 = 3 total
        assert len(result.events) == 3
        source_systems = [e.source_system for e in result.events]
        assert "adt_vendor_x" in source_systems
        assert "claims_clearinghouse" in source_systems
