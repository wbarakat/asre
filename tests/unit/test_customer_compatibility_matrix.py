"""Customer compatibility tests for config variability and extensibility."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from asre.canonicalize.event_type_resolver import EventTypeResolver
from asre.canonicalize.stage import CanonicalizeStage
from asre.canonicalize.store import CanonicalEventStore
from asre.config.loader import load_config
from asre.config.source_schema import EventTypeRules
from asre.ingest.adapter_factory import create_adapter
from asre.ingest.stage import IngestStage
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.pipeline.runner import PipelineContext


def _make_source_config(
    *,
    source_name: str,
    patient_key: str,
    event_ts: str,
    source_record_id: str,
    facility_raw: str,
    patient_class: str,
    source_event_field: str,
    source_event_map: dict[str, str],
) -> dict[str, Any]:
    return {
        "name": source_name,
        "type": "adt",
        "source": {
            "table": "raw_events",
            "incremental_key": event_ts,
        },
        "field_mappings": {
            "patient_key": patient_key,
            "event_ts": event_ts,
            "source_record_id": source_record_id,
            "facility_raw": facility_raw,
            "patient_class": patient_class,
        },
        "event_type_rules": {
            "source_field": source_event_field,
            "mappings": source_event_map,
            "admit_flag_expression": "event_type IN ('ADMIT', 'TRANSFER_IN')",
            "discharge_flag_expression": "event_type IN ('DISCHARGE')",
        },
    }


def _make_customer_dir(
    tmp_path: Path,
    *,
    customer_id: str,
    warehouse_type: str = "postgres",
) -> Path:
    customer_dir = tmp_path / customer_id
    customer_dir.mkdir()
    (customer_dir / "sources").mkdir()

    config_yaml = {
        "customer": {
            "customer_id": customer_id,
            "customer_name": "Compatibility Test Customer",
        },
        "warehouse": {
            "type": warehouse_type,
            "connection": {},
        },
    }
    (customer_dir / "config.yaml").write_text(yaml.dump(config_yaml))
    return customer_dir


def _run_ingest_and_canonicalize(
    source_config: dict[str, Any],
    raw_record: dict[str, Any],
) -> CanonicalEvent:
    adapter = MagicMock()
    adapter.read_source.return_value = [raw_record]
    adapter.get_watermark.return_value = None

    ingest_context = PipelineContext(
        run_id="run_cfg_matrix_ingest",
        config={
            "sources": [source_config],
            "schedule": {"lookback_buffer": {"default": "24h"}},
            "adapter": adapter,
        },
        mode="full",
    )

    ingest_stage = IngestStage()
    ingest_stage.run(EventBatch(batch_id="batch_ingest", events=[]), ingest_context)

    canonical_context = PipelineContext(
        run_id="run_cfg_matrix_canonicalize",
        config={
            "sources": [source_config],
            "raw_records": ingest_stage.raw_records,
        },
        mode="full",
    )

    canonical_stage = CanonicalizeStage()
    result = canonical_stage.run(
        EventBatch(batch_id="batch_canonical", events=[]),
        canonical_context,
    )
    assert len(result.events) == 1
    return result.events[0]


def _make_event(event_type: str = "UNKNOWN") -> CanonicalEvent:
    return CanonicalEvent(
        event_id="evt-compat",
        patient_key="PAT-001",
        event_type=event_type,
        event_ts=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        source_system="adt_vendor_x",
        source_record_id="MSG-001",
        facility_raw="Test Hospital",
        ingested_at=datetime.now(tz=timezone.utc),
        batch_id="batch-001",
    )


class TestWarehouseEnvironmentMatrix:
    @pytest.mark.parametrize(
        ("warehouse_type", "credentials", "expected_adapter"),
        [
            (
                "postgres",
                {
                    "host": "localhost",
                    "port": 5432,
                    "database": "asre_dev",
                    "user": "asre",
                    "password": "secret",
                    "schema": "public",
                },
                "PostgresAdapter",
            ),
            (
                "snowflake",
                {
                    "account": "myaccount",
                    "user": "asre",
                    "password": "secret",
                    "database": "analytics",
                    "schema": "PUBLIC",
                    "warehouse": "COMPUTE_WH",
                },
                "SnowflakeAdapter",
            ),
            (
                "bigquery",
                {
                    "project": "asre-project",
                    "dataset": "asre_dataset",
                    "location": "US",
                },
                "BigQueryAdapter",
            ),
            (
                "redshift",
                {
                    "host": "cluster.example.amazonaws.com",
                    "port": 5439,
                    "database": "analytics",
                    "user": "asre",
                    "password": "secret",
                    "schema": "public",
                },
                "RedshiftAdapter",
            ),
        ],
    )
    def test_load_config_accepts_each_warehouse_env_shape(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        warehouse_type: str,
        credentials: dict[str, Any],
        expected_adapter: str,
    ) -> None:
        _make_customer_dir(
            tmp_path,
            customer_id="env_matrix_customer",
            warehouse_type="postgres",
        )

        monkeypatch.setenv("ASRE_WAREHOUSE_TYPE", warehouse_type)
        monkeypatch.setenv("ASRE_WAREHOUSE_CREDENTIALS", json.dumps(credentials))

        config = load_config(str(tmp_path), "env_matrix_customer")

        assert config.warehouse.type == warehouse_type
        assert config.warehouse.connection == credentials

        adapter = create_adapter(config.warehouse.type, config.warehouse.connection)
        assert adapter.__class__.__name__ == expected_adapter

    @pytest.mark.parametrize(
        ("warehouse_type", "connection_string", "expected"),
        [
            (
                "postgres",
                "postgresql://asre:secret@db.example.com:5433/asre_dev?schema=analytics",
                {
                    "host": "db.example.com",
                    "port": 5433,
                    "database": "asre_dev",
                    "user": "asre",
                    "password": "secret",
                    "schema": "analytics",
                },
            ),
            (
                "redshift",
                "redshift://asre:secret@cluster.example.com:5440/asre_rs?schema=public",
                {
                    "host": "cluster.example.com",
                    "port": 5440,
                    "database": "asre_rs",
                    "user": "asre",
                    "password": "secret",
                    "schema": "public",
                },
            ),
        ],
    )
    def test_connection_string_credentials_use_config_warehouse_type(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        warehouse_type: str,
        connection_string: str,
        expected: dict[str, Any],
    ) -> None:
        _make_customer_dir(
            tmp_path,
            customer_id="dsn_customer",
            warehouse_type=warehouse_type,
        )

        monkeypatch.delenv("ASRE_WAREHOUSE_TYPE", raising=False)
        monkeypatch.setenv("ASRE_WAREHOUSE_CREDENTIALS", connection_string)

        config = load_config(str(tmp_path), "dsn_customer")

        assert config.warehouse.type == warehouse_type
        assert config.warehouse.connection == expected


class TestSourceSchemaVariability:
    @pytest.mark.parametrize(
        ("source_config", "raw_record", "expected_patient_key", "expected_event_type"),
        [
            (
                _make_source_config(
                    source_name="adt_vendor_alpha",
                    patient_key="patient_mrn",
                    event_ts="message_ts",
                    source_record_id="message_id",
                    facility_raw="sending_facility",
                    patient_class="patient_class",
                    source_event_field="hl7_event",
                    source_event_map={"A01": "ADMIT"},
                ),
                {
                    "patient_mrn": "P-100",
                    "message_ts": "2026-01-01T10:00:00+00:00",
                    "message_id": "MSG-100",
                    "sending_facility": "General Hospital",
                    "patient_class": "I",
                    "hl7_event": "A01",
                    "attending_provider_id": "NPI-9001",
                    "unit_code": "3W",
                },
                "P-100",
                "ADMIT",
            ),
            (
                _make_source_config(
                    source_name="adt_vendor_beta",
                    patient_key="member_id",
                    event_ts="occurred_at",
                    source_record_id="event_uuid",
                    facility_raw="site_name",
                    patient_class="class_code",
                    source_event_field="event_code",
                    source_event_map={"IN": "ADMIT"},
                ),
                {
                    "member_id": "M-222",
                    "occurred_at": "2026-01-02T06:30:00+00:00",
                    "event_uuid": "EVT-222",
                    "site_name": "Regional Medical Center",
                    "class_code": "I",
                    "event_code": "IN",
                    "care_team": ["hospitalist", "case_mgmt"],
                    "payload_version": 3,
                },
                "M-222",
                "ADMIT",
            ),
        ],
    )
    def test_customer_specific_column_shapes_map_to_same_canonical_contract(
        self,
        source_config: dict[str, Any],
        raw_record: dict[str, Any],
        expected_patient_key: str,
        expected_event_type: str,
    ) -> None:
        event = _run_ingest_and_canonicalize(source_config, raw_record)

        assert event.patient_key == expected_patient_key
        assert event.event_type == expected_event_type
        assert event._raw_payload is not None
        for key, value in raw_record.items():
            assert event._raw_payload[key] == value


class TestExtraColumnRetentionContract:
    def test_unmapped_source_columns_remain_available_in_canonical_history_payload(
        self,
    ) -> None:
        source_config = _make_source_config(
            source_name="adt_vendor_extra_cols",
            patient_key="patient_id",
            event_ts="event_ts",
            source_record_id="msg_id",
            facility_raw="facility_name",
            patient_class="patient_class",
            source_event_field="hl7_event",
            source_event_map={"A01": "ADMIT"},
        )
        raw_record = {
            "patient_id": "PAT-777",
            "event_ts": "2026-01-05T13:00:00+00:00",
            "msg_id": "MSG-777",
            "facility_name": "Mercy West",
            "patient_class": "I",
            "hl7_event": "A01",
            "care_pathway": "cardiology",
            "custom_score": 0.92,
            "nested": {"bed": "12A", "wing": "north"},
        }

        event = _run_ingest_and_canonicalize(source_config, raw_record)

        adapter = MagicMock()
        adapter.warehouse_type = "postgres"
        adapter.execute_ddl = MagicMock()
        adapter.write_records = MagicMock(return_value=1)

        store = CanonicalEventStore(adapter)
        store.upsert_events([event])

        assert adapter.write_records.called
        persisted_record = adapter.write_records.call_args[0][1][0]
        payload = json.loads(persisted_record["raw_payload"])

        assert payload["care_pathway"] == "cardiology"
        assert payload["custom_score"] == 0.92
        assert payload["nested"] == {"bed": "12A", "wing": "north"}


class TestAdtEventTypeExtensibility:
    def test_additional_hl7_trigger_code_can_be_configured_without_code_changes(
        self,
    ) -> None:
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"A14": "TRANSFER_IN"},
            admit_flag_expression="event_type IN ('TRANSFER_IN')",
        )
        resolver = EventTypeResolver(rules)

        event = _make_event()
        result = resolver.resolve(event, {"hl7_event": "A14"})

        assert result.event_type == "TRANSFER_IN"
        assert result.admit_flag is True

    def test_custom_non_anchor_event_type_flows_through_but_keeps_flags_false(self) -> None:
        rules = EventTypeRules(
            source_field="hl7_event",
            mappings={"Z90": "BED_ASSIGNMENT"},
            admit_flag_expression="event_type IN ('ADMIT', 'ED_ARRIVAL')",
            discharge_flag_expression="event_type IN ('DISCHARGE', 'ED_DEPARTURE')",
        )
        resolver = EventTypeResolver(rules)

        event = _make_event()
        result = resolver.resolve(event, {"hl7_event": "Z90"})

        assert result.event_type == "BED_ASSIGNMENT"
        assert result.admit_flag is False
        assert result.discharge_flag is False

    def test_canonicalize_stage_accepts_customer_specific_custom_event_mapping(self) -> None:
        source_config = _make_source_config(
            source_name="adt_vendor_custom_events",
            patient_key="patient_id",
            event_ts="event_ts",
            source_record_id="msg_id",
            facility_raw="facility_name",
            patient_class="patient_class",
            source_event_field="hl7_event",
            source_event_map={"A40": "BED_ASSIGNMENT"},
        )
        raw_record = {
            "patient_id": "PAT-990",
            "event_ts": "2026-01-10T09:15:00+00:00",
            "msg_id": "MSG-990",
            "facility_name": "Central Health",
            "patient_class": "I",
            "hl7_event": "A40",
        }

        event = _run_ingest_and_canonicalize(source_config, raw_record)

        assert event.event_type == "BED_ASSIGNMENT"
        assert event.admit_flag is False
        assert event.discharge_flag is False
