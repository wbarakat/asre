"""Tests for global config Pydantic schema (US-012)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from asre.config.schema import (
    AlertingConfig,
    ConfidenceScoringConfig,
    CustomerConfig,
    DeduplicationConfig,
    EncounterStitchingConfig,
    EpisodeStitchingConfig,
    FacilityNormalizationConfig,
    GlobalConfig,
    ReconciliationConfig,
    ScheduleConfig,
    WarehouseConfig,
)


class TestWarehouseConfig:
    def test_valid_warehouse(self) -> None:
        cfg = WarehouseConfig(
            type="snowflake",
            connection={
                "account": "test_account",
                "database": "test_db",
                "schema": "test_schema",
            },
        )
        assert cfg.type == "snowflake"
        assert cfg.connection["account"] == "test_account"

    def test_warehouse_type_required(self) -> None:
        with pytest.raises(ValidationError):
            WarehouseConfig(connection={"account": "x"})  # type: ignore[call-arg]

    def test_connection_required(self) -> None:
        with pytest.raises(ValidationError):
            WarehouseConfig(type="snowflake")  # type: ignore[call-arg]


class TestScheduleConfig:
    def test_defaults(self) -> None:
        cfg = ScheduleConfig()
        assert cfg.mode == "incremental"
        assert cfg.lookback_buffer is not None
        assert cfg.lookback_buffer["default"] == "24h"

    def test_custom_mode(self) -> None:
        cfg = ScheduleConfig(mode="full")
        assert cfg.mode == "full"

    def test_custom_lookback_buffer(self) -> None:
        cfg = ScheduleConfig(lookback_buffer={"default": "48h", "adt": "12h", "claims": "72h"})
        assert cfg.lookback_buffer["adt"] == "12h"
        assert cfg.lookback_buffer["claims"] == "72h"


class TestEncounterStitchingConfig:
    def test_defaults(self) -> None:
        cfg = EncounterStitchingConfig()
        assert cfg.time_window_hours == 48
        assert cfg.facility_must_match is True
        assert cfg.patient_class_transitions is not None
        assert len(cfg.patient_class_transitions) > 0
        assert cfg.same_timestamp_tiebreaker is not None

    def test_custom_time_window(self) -> None:
        cfg = EncounterStitchingConfig(time_window_hours=72)
        assert cfg.time_window_hours == 72

    def test_custom_facility_must_match(self) -> None:
        cfg = EncounterStitchingConfig(facility_must_match=False)
        assert cfg.facility_must_match is False


class TestDeduplicationConfig:
    def test_defaults(self) -> None:
        cfg = DeduplicationConfig()
        assert cfg.match_fields == ["patient_key", "event_type", "facility_canonical_id"]
        assert cfg.time_tolerance_minutes == 30

    def test_custom_values(self) -> None:
        cfg = DeduplicationConfig(
            match_fields=["patient_key", "event_type"],
            time_tolerance_minutes=60,
        )
        assert len(cfg.match_fields) == 2
        assert cfg.time_tolerance_minutes == 60


class TestReconciliationConfig:
    def test_defaults(self) -> None:
        cfg = ReconciliationConfig()
        assert cfg.timestamp_priority is not None
        assert cfg.classification_priority is not None
        assert cfg.timestamp_tolerance_hours == 24

    def test_source_priorities(self) -> None:
        cfg = ReconciliationConfig()
        # ADT should have highest timestamp priority
        assert cfg.timestamp_priority["adt"] > cfg.timestamp_priority["claims"]
        assert cfg.timestamp_priority["claims"] > cfg.timestamp_priority["auth"]
        # Claims should have highest classification priority
        assert cfg.classification_priority["claims"] > cfg.classification_priority["adt"]
        assert cfg.classification_priority["adt"] > cfg.classification_priority["auth"]


class TestEpisodeStitchingConfig:
    def test_defaults(self) -> None:
        cfg = EpisodeStitchingConfig()
        assert cfg.readmission_window_days == 30
        assert cfg.post_acute_linkage_days == 14
        assert cfg.planned_return_days == 90
        assert cfg.ed_bounceback_days == 7


class TestEncounterStitchingConfig:
    def test_defaults(self) -> None:
        from asre.config.schema import EncounterStitchingConfig

        cfg = EncounterStitchingConfig()
        assert cfg.history_lookback_days == 90
        assert cfg.use_canonical_history is True


class TestFacilityNormalizationConfig:
    def test_defaults(self) -> None:
        cfg = FacilityNormalizationConfig()
        assert cfg.fuzzy_threshold == 0.85
        assert cfg.abbreviations is not None
        assert len(cfg.abbreviations) > 0
        assert cfg.use_npi_registry is True
        assert cfg.use_ccn_registry is True
        assert cfg.registry_path is None

    def test_custom_threshold(self) -> None:
        cfg = FacilityNormalizationConfig(fuzzy_threshold=0.90)
        assert cfg.fuzzy_threshold == 0.90

    def test_custom_registry_path(self) -> None:
        cfg = FacilityNormalizationConfig(registry_path="/tmp/facility_registry.csv")
        assert cfg.registry_path == "/tmp/facility_registry.csv"


class TestConfidenceScoringConfig:
    def test_defaults(self) -> None:
        cfg = ConfidenceScoringConfig()
        # Signal weights
        assert cfg.signal_weights["HAS_CLAIMS"] == 30
        assert cfg.signal_weights["HAS_ADT_ADMIT"] == 20
        assert cfg.signal_weights["HAS_ADT_DISCHARGE"] == 10
        assert cfg.signal_weights["HAS_AUTH"] == 10
        assert cfg.signal_weights["FACILITY_RESOLVED"] == 5
        assert cfg.signal_weights["TIMESTAMPS_CONSISTENT"] == 15
        assert cfg.signal_weights["PATIENT_CLASS_CONSISTENT"] == 10
        # Penalty values
        assert cfg.penalties["MISSING_DISCHARGE"] == -0.15
        assert cfg.penalties["ORPHAN_DISCHARGE"] == -0.20
        assert cfg.penalties["TIMESTAMP_MISMATCH"] == -0.10
        # Stale encounter thresholds
        assert cfg.stale_encounter_thresholds is not None
        assert cfg.stale_encounter_thresholds["acute"] == 30
        assert cfg.stale_encounter_thresholds["ltach"] == 90
        assert cfg.stale_encounter_thresholds["snf"] == 120


class TestAlertingConfig:
    def test_defaults(self) -> None:
        cfg = AlertingConfig()
        assert cfg.webhook_urls == []
        assert cfg.block_on_statuses == ["fail"]
        assert cfg.thresholds is not None

    def test_custom_webhooks(self) -> None:
        cfg = AlertingConfig(webhook_urls=["https://hooks.example.com/alert"])
        assert len(cfg.webhook_urls) == 1

    def test_thresholds_defaults(self) -> None:
        cfg = AlertingConfig()
        assert cfg.thresholds["duplicate_rate_warn"] == 0.05
        assert cfg.thresholds["duplicate_rate_fail"] == 0.15


class TestCustomerConfig:
    def test_valid_customer(self) -> None:
        cfg = CustomerConfig(customer_id="test_customer", customer_name="Test Customer")
        assert cfg.customer_id == "test_customer"
        assert cfg.customer_name == "Test Customer"

    def test_customer_id_required(self) -> None:
        with pytest.raises(ValidationError):
            CustomerConfig(customer_name="Test")  # type: ignore[call-arg]


class TestGlobalConfig:
    def test_minimal_valid_config(self) -> None:
        cfg = GlobalConfig(
            customer=CustomerConfig(customer_id="test", customer_name="Test"),
            warehouse=WarehouseConfig(
                type="postgres",
                connection={"host": "localhost", "port": 5432, "database": "asre"},
            ),
        )
        assert cfg.customer.customer_id == "test"
        assert cfg.warehouse.type == "postgres"
        # All sub-configs should have defaults
        assert cfg.schedule is not None
        assert cfg.encounter_stitching is not None
        assert cfg.deduplication is not None
        assert cfg.reconciliation is not None
        assert cfg.episode_stitching is not None
        assert cfg.facility_normalization is not None
        assert cfg.confidence_scoring is not None
        assert cfg.alerting is not None

    def test_customer_required(self) -> None:
        with pytest.raises(ValidationError):
            GlobalConfig(  # type: ignore[call-arg]
                warehouse=WarehouseConfig(
                    type="postgres",
                    connection={"host": "localhost"},
                ),
            )

    def test_warehouse_required(self) -> None:
        with pytest.raises(ValidationError):
            GlobalConfig(  # type: ignore[call-arg]
                customer=CustomerConfig(customer_id="t", customer_name="T"),
            )

    def test_all_defaults_populated(self) -> None:
        cfg = GlobalConfig(
            customer=CustomerConfig(customer_id="t", customer_name="T"),
            warehouse=WarehouseConfig(type="postgres", connection={"host": "localhost"}),
        )
        assert cfg.schedule.mode == "incremental"
        assert cfg.encounter_stitching.time_window_hours == 48
        assert cfg.deduplication.time_tolerance_minutes == 30
        assert cfg.reconciliation.timestamp_tolerance_hours == 24
        assert cfg.episode_stitching.readmission_window_days == 30
        assert cfg.facility_normalization.fuzzy_threshold == 0.85
        assert cfg.confidence_scoring.signal_weights["HAS_CLAIMS"] == 30
        assert cfg.alerting.webhook_urls == []

    def test_invalid_config_raises(self) -> None:
        with pytest.raises(ValidationError):
            GlobalConfig()  # type: ignore[call-arg]

    def test_override_sub_configs(self) -> None:
        cfg = GlobalConfig(
            customer=CustomerConfig(customer_id="t", customer_name="T"),
            warehouse=WarehouseConfig(type="postgres", connection={"host": "localhost"}),
            schedule=ScheduleConfig(mode="full"),
            encounter_stitching=EncounterStitchingConfig(time_window_hours=24),
        )
        assert cfg.schedule.mode == "full"
        assert cfg.encounter_stitching.time_window_hours == 24
