"""Tests for pipeline config builder and adapter factory."""

from __future__ import annotations

from typing import Any, Type

import pytest

from asre.config.facility_alias_schema import FacilityAlias, FacilityAliasConfig
from asre.config.schema import (
    AlertingConfig,
    CustomerConfig,
    FacilityNormalizationConfig,
    GlobalConfig,
    ScheduleConfig,
    WarehouseConfig,
)
from asre.config.source_schema import SourceConfig


def _make_source_config() -> dict[str, Any]:
    return {
        "name": "adt_vendor_x",
        "type": "adt",
        "source": {"table": "raw_adt_events", "incremental_key": "message_ts"},
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
    }


class TestBuildPipelineConfig:
    def test_converts_models_to_plain_dicts(self) -> None:
        from asre.config.pipeline_config_builder import build_pipeline_config

        global_config = GlobalConfig(
            customer=CustomerConfig(
                customer_id="test_customer",
                customer_name="Test Health System",
            ),
            warehouse=WarehouseConfig(type="postgres", connection={}),
            schedule=ScheduleConfig(),
            alerting=AlertingConfig(),
            facility_normalization=FacilityNormalizationConfig(),
        )
        global_config.sources = [SourceConfig(**_make_source_config())]
        global_config.facility_aliases = FacilityAliasConfig(
            facilities=[
                FacilityAlias(
                    canonical_id="FAC_001",
                    canonical_name="Test Hospital",
                    aliases=["TEST HOSP"],
                )
            ]
        )

        config = build_pipeline_config(global_config)

        assert isinstance(config["sources"][0], dict)
        assert isinstance(config["schedule"], dict)
        assert isinstance(config["alerting"], dict)
        assert isinstance(config["facility_normalization"], dict)
        assert config["facility_aliases"] is global_config.facility_aliases


class TestAdapterFactory:
    @pytest.mark.parametrize(
        ("warehouse_type", "expected_cls"),
        [
            ("postgres", "PostgresAdapter"),
            ("snowflake", "SnowflakeAdapter"),
            ("bigquery", "BigQueryAdapter"),
            ("redshift", "RedshiftAdapter"),
        ],
    )
    def test_create_adapter_returns_expected_type(
        self, warehouse_type: str, expected_cls: str
    ) -> None:
        from asre.ingest.adapter_factory import create_adapter

        adapter = create_adapter(warehouse_type, {})
        assert adapter.__class__.__name__ == expected_cls

    def test_create_adapter_rejects_unknown_type(self) -> None:
        from asre.ingest.adapter_factory import create_adapter

        with pytest.raises(ValueError):
            create_adapter("oracle", {})
