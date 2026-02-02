"""Tests for US-016: Example customer config validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from asre.config.loader import load_config
from asre.config.schema import GlobalConfig
from asre.config.source_schema import SourceConfig
from asre.config.facility_alias_schema import FacilityAliasConfig, FacilityAlias

CUSTOMER_CONFIG_PATH = str(Path(__file__).parent.parent.parent / "customer_config")
CUSTOMER_ID = "test_customer"


@pytest.fixture(autouse=True)
def _set_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set placeholder env vars that the example config might reference."""
    monkeypatch.setenv("WAREHOUSE_HOST", "localhost")
    monkeypatch.setenv("WAREHOUSE_PORT", "5432")
    monkeypatch.setenv("WAREHOUSE_DATABASE", "asre_test")
    monkeypatch.setenv("WAREHOUSE_USER", "asre_user")
    monkeypatch.setenv("WAREHOUSE_PASSWORD", "secret_password")
    monkeypatch.setenv("WAREHOUSE_SCHEMA", "public")
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/alert")


class TestExampleConfigStructure:
    """Tests that example config directory has expected structure."""

    def test_customer_dir_exists(self) -> None:
        customer_dir = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID
        assert customer_dir.is_dir(), f"Missing directory: {customer_dir}"

    def test_config_yaml_exists(self) -> None:
        config_file = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID / "config.yaml"
        assert config_file.is_file(), f"Missing file: {config_file}"

    def test_sources_dir_exists(self) -> None:
        sources_dir = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID / "sources"
        assert sources_dir.is_dir(), f"Missing directory: {sources_dir}"

    def test_adt_source_exists(self) -> None:
        adt_file = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID / "sources" / "adt_vendor_x.yaml"
        assert adt_file.is_file(), f"Missing file: {adt_file}"

    def test_claims_source_exists(self) -> None:
        claims_file = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID / "sources" / "claims_clearinghouse.yaml"
        assert claims_file.is_file(), f"Missing file: {claims_file}"

    def test_auth_source_exists(self) -> None:
        auth_file = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID / "sources" / "auth_portal.yaml"
        assert auth_file.is_file(), f"Missing file: {auth_file}"

    def test_facility_aliases_exists(self) -> None:
        aliases_file = Path(CUSTOMER_CONFIG_PATH) / CUSTOMER_ID / "facility_aliases.yaml"
        assert aliases_file.is_file(), f"Missing file: {aliases_file}"


class TestExampleConfigLoads:
    """Tests that all example configs load and validate successfully."""

    def test_load_config_succeeds(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        assert isinstance(config, GlobalConfig)

    def test_customer_section(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        assert config.customer.customer_id == "test_customer"
        assert config.customer.customer_name != ""

    def test_warehouse_section(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        assert config.warehouse.type == "postgres"
        assert "host" in config.warehouse.connection

    def test_all_sections_populated(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        assert config.schedule is not None
        assert config.encounter_stitching is not None
        assert config.deduplication is not None
        assert config.reconciliation is not None
        assert config.episode_stitching is not None
        assert config.facility_normalization is not None
        assert config.confidence_scoring is not None
        assert config.alerting is not None


class TestExampleSources:
    """Tests that source configs have correct types and required fields."""

    def test_three_sources_loaded(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        assert len(config.sources) == 3

    def test_adt_source_type(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        adt_sources = [s for s in config.sources if s.type == "adt"]
        assert len(adt_sources) == 1
        adt = adt_sources[0]
        assert adt.name == "adt_vendor_x"
        assert adt.event_type_rules is not None
        assert adt.field_mappings.patient_key != ""

    def test_claims_source_type(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        claims_sources = [s for s in config.sources if s.type == "claims"]
        assert len(claims_sources) == 1
        claims = claims_sources[0]
        assert claims.name == "claims_clearinghouse"
        assert claims.paired_events is not None
        assert claims.paired_events.admit.event_ts != ""
        assert claims.paired_events.discharge.event_ts != ""

    def test_auth_source_type(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        auth_sources = [s for s in config.sources if s.type == "auth"]
        assert len(auth_sources) == 1
        auth = auth_sources[0]
        assert auth.name == "auth_portal"
        assert auth.auth_status_map is not None
        assert len(auth.auth_status_map.mappings) > 0

    def test_adt_has_event_type_mappings(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        adt = [s for s in config.sources if s.type == "adt"][0]
        mappings = adt.event_type_rules.mappings
        # Should have standard HL7 event type mappings
        assert "A01" in mappings
        assert "A03" in mappings

    def test_adt_has_conditional_mappings(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        adt = [s for s in config.sources if s.type == "adt"][0]
        assert len(adt.event_type_rules.conditional_mappings) > 0

    def test_claims_has_patient_class_rules(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        claims = [s for s in config.sources if s.type == "claims"][0]
        assert claims.patient_class_rules is not None
        assert len(claims.patient_class_rules.conditions) > 0

    def test_adt_has_filters(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        adt = [s for s in config.sources if s.type == "adt"][0]
        assert adt.filters is not None
        assert adt.filters.exclude is not None


class TestExampleFacilityAliases:
    """Tests that facility aliases config is valid."""

    def test_facility_aliases_loaded(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        assert config.facility_aliases is not None
        assert isinstance(config.facility_aliases, FacilityAliasConfig)

    def test_has_sample_facilities(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        aliases = config.facility_aliases
        assert aliases is not None
        assert len(aliases.facilities) >= 3

    def test_facilities_have_required_fields(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        aliases = config.facility_aliases
        assert aliases is not None
        for facility in aliases.facilities:
            assert facility.canonical_id != ""
            assert facility.canonical_name != ""

    def test_some_facilities_have_aliases(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        aliases = config.facility_aliases
        assert aliases is not None
        facilities_with_aliases = [f for f in aliases.facilities if len(f.aliases) > 0]
        assert len(facilities_with_aliases) >= 1

    def test_some_facilities_have_npi(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        aliases = config.facility_aliases
        assert aliases is not None
        facilities_with_npi = [f for f in aliases.facilities if f.npi is not None]
        assert len(facilities_with_npi) >= 1

    def test_facility_types_populated(self) -> None:
        config = load_config(CUSTOMER_CONFIG_PATH, CUSTOMER_ID)
        aliases = config.facility_aliases
        assert aliases is not None
        facilities_with_type = [f for f in aliases.facilities if f.facility_type is not None]
        assert len(facilities_with_type) >= 1
