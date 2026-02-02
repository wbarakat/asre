"""Tests for YAML config loader with env var substitution (US-015)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from asre.config.loader import load_config


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    """Create a minimal valid customer config directory."""
    customer_dir = tmp_path / "test_customer"
    customer_dir.mkdir()
    sources_dir = customer_dir / "sources"
    sources_dir.mkdir()

    # config.yaml
    config_yaml = {
        "customer": {"customer_id": "test_customer", "customer_name": "Test Customer"},
        "warehouse": {"type": "postgres", "connection": {"host": "localhost", "port": 5432}},
    }
    (customer_dir / "config.yaml").write_text(yaml.dump(config_yaml))

    # sources/adt_vendor.yaml
    adt_yaml = {
        "name": "adt_vendor",
        "type": "adt",
        "source": {"table": "raw.adt_events", "incremental_key": "message_ts"},
        "field_mappings": {
            "patient_key": "patient_id",
            "event_ts": "message_ts",
            "source_record_id": "message_control_id",
            "facility_raw": "sending_facility",
        },
        "event_type_rules": {
            "source_field": "hl7_event",
            "mappings": {"A01": "ADMIT", "A03": "DISCHARGE"},
        },
    }
    (sources_dir / "adt_vendor.yaml").write_text(yaml.dump(adt_yaml))

    return tmp_path


@pytest.fixture()
def config_dir_with_aliases(config_dir: Path) -> Path:
    """Config dir that also has facility_aliases.yaml."""
    customer_dir = config_dir / "test_customer"
    aliases_yaml = {
        "facilities": [
            {
                "canonical_id": "FAC_001",
                "canonical_name": "St. Mary's Hospital",
                "aliases": ["ST MARYS", "SAINT MARYS HOSPITAL"],
            }
        ]
    }
    (customer_dir / "facility_aliases.yaml").write_text(yaml.dump(aliases_yaml))
    return config_dir


class TestLoadConfigValid:
    """Test loading valid configurations."""

    def test_load_config_returns_global_config(self, config_dir: Path) -> None:
        result = load_config(str(config_dir), "test_customer")
        from asre.config.schema import GlobalConfig

        assert isinstance(result, GlobalConfig)

    def test_load_config_customer_fields(self, config_dir: Path) -> None:
        result = load_config(str(config_dir), "test_customer")
        assert result.customer.customer_id == "test_customer"
        assert result.customer.customer_name == "Test Customer"

    def test_load_config_warehouse_fields(self, config_dir: Path) -> None:
        result = load_config(str(config_dir), "test_customer")
        assert result.warehouse.type == "postgres"
        assert result.warehouse.connection["host"] == "localhost"

    def test_load_config_defaults_applied(self, config_dir: Path) -> None:
        result = load_config(str(config_dir), "test_customer")
        # Sub-configs with defaults should be populated
        assert result.schedule.mode == "incremental"
        assert result.encounter_stitching.time_window_hours == 48


class TestSourceConfigLoading:
    """Test loading source configs from sources/ directory."""

    def test_source_configs_loaded(self, config_dir: Path) -> None:
        result = load_config(str(config_dir), "test_customer")
        assert hasattr(result, "sources")
        assert len(result.sources) == 1

    def test_source_config_fields(self, config_dir: Path) -> None:
        result = load_config(str(config_dir), "test_customer")
        source = result.sources[0]
        assert source.name == "adt_vendor"
        assert source.type == "adt"
        assert source.source.table == "raw.adt_events"

    def test_multiple_sources_loaded(self, config_dir: Path) -> None:
        """Add a claims source and verify both load."""
        claims_yaml = {
            "name": "claims_ch",
            "type": "claims",
            "source": {"table": "raw.claims", "incremental_key": "processed_date"},
            "field_mappings": {
                "patient_key": "member_id",
                "event_ts": "admit_date",
                "source_record_id": "claim_id",
            },
            "event_type_rules": {
                "source_field": "claim_type",
                "mappings": {"IP": "CLAIM_ADMIT"},
            },
            "paired_events": {
                "admit": {"event_ts": "admit_date", "event_type": "CLAIM_ADMIT"},
                "discharge": {"event_ts": "discharge_date", "event_type": "CLAIM_DISCHARGE"},
            },
        }
        sources_dir = config_dir / "test_customer" / "sources"
        (sources_dir / "claims_ch.yaml").write_text(yaml.dump(claims_yaml))

        result = load_config(str(config_dir), "test_customer")
        assert len(result.sources) == 2
        names = {s.name for s in result.sources}
        assert names == {"adt_vendor", "claims_ch"}


class TestFacilityAliasLoading:
    """Test loading facility_aliases.yaml."""

    def test_facility_aliases_loaded(self, config_dir_with_aliases: Path) -> None:
        result = load_config(str(config_dir_with_aliases), "test_customer")
        assert hasattr(result, "facility_aliases")
        assert result.facility_aliases is not None
        assert len(result.facility_aliases.facilities) == 1

    def test_facility_aliases_optional(self, config_dir: Path) -> None:
        """Config without facility_aliases.yaml should still load."""
        result = load_config(str(config_dir), "test_customer")
        assert result.facility_aliases is None

    def test_facility_alias_fields(self, config_dir_with_aliases: Path) -> None:
        result = load_config(str(config_dir_with_aliases), "test_customer")
        fac = result.facility_aliases.facilities[0]
        assert fac.canonical_id == "FAC_001"
        assert fac.canonical_name == "St. Mary's Hospital"
        assert "ST MARYS" in fac.aliases


class TestEnvVarSubstitution:
    """Test ${ENV_VAR} substitution in YAML values."""

    def test_env_var_substituted(self, config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TEST_DB_HOST", "prod-db.example.com")
        config_yaml = {
            "customer": {"customer_id": "test_customer", "customer_name": "Test Customer"},
            "warehouse": {"type": "postgres", "connection": {"host": "${TEST_DB_HOST}", "port": 5432}},
        }
        (config_dir / "test_customer" / "config.yaml").write_text(yaml.dump(config_yaml))

        result = load_config(str(config_dir), "test_customer")
        assert result.warehouse.connection["host"] == "prod-db.example.com"

    def test_env_var_in_nested_value(self, config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DB_PASSWORD", "secret123")
        config_yaml = {
            "customer": {"customer_id": "test_customer", "customer_name": "Test Customer"},
            "warehouse": {
                "type": "postgres",
                "connection": {"host": "localhost", "port": 5432, "password": "${DB_PASSWORD}"},
            },
        }
        (config_dir / "test_customer" / "config.yaml").write_text(yaml.dump(config_yaml))

        result = load_config(str(config_dir), "test_customer")
        assert result.warehouse.connection["password"] == "secret123"

    def test_multiple_env_vars_in_one_value(
        self, config_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("DB_USER", "admin")
        monkeypatch.setenv("DB_HOST", "db.local")
        config_yaml = {
            "customer": {"customer_id": "test_customer", "customer_name": "Test Customer"},
            "warehouse": {
                "type": "postgres",
                "connection": {"host": "localhost", "port": 5432, "uri": "${DB_USER}@${DB_HOST}"},
            },
        }
        (config_dir / "test_customer" / "config.yaml").write_text(yaml.dump(config_yaml))

        result = load_config(str(config_dir), "test_customer")
        assert result.warehouse.connection["uri"] == "admin@db.local"

    def test_env_var_in_source_config(self, config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADT_TABLE", "production.adt_events")
        adt_yaml = {
            "name": "adt_vendor",
            "type": "adt",
            "source": {"table": "${ADT_TABLE}", "incremental_key": "message_ts"},
            "field_mappings": {
                "patient_key": "patient_id",
                "event_ts": "message_ts",
                "source_record_id": "message_control_id",
            },
            "event_type_rules": {
                "source_field": "hl7_event",
                "mappings": {"A01": "ADMIT"},
            },
        }
        (config_dir / "test_customer" / "sources" / "adt_vendor.yaml").write_text(
            yaml.dump(adt_yaml)
        )

        result = load_config(str(config_dir), "test_customer")
        assert result.sources[0].source.table == "production.adt_events"


class TestErrorHandling:
    """Test error cases."""

    def test_missing_config_dir(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="test_customer"):
            load_config(str(tmp_path), "test_customer")

    def test_missing_config_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "test_customer").mkdir()
        with pytest.raises(FileNotFoundError, match="config.yaml"):
            load_config(str(tmp_path), "test_customer")

    def test_missing_env_var_raises_error(self, config_dir: Path) -> None:
        config_yaml = {
            "customer": {"customer_id": "test_customer", "customer_name": "Test Customer"},
            "warehouse": {
                "type": "postgres",
                "connection": {"host": "${NONEXISTENT_VAR}", "port": 5432},
            },
        }
        (config_dir / "test_customer" / "config.yaml").write_text(yaml.dump(config_yaml))

        with pytest.raises(ValueError, match="NONEXISTENT_VAR"):
            load_config(str(config_dir), "test_customer")

    def test_malformed_yaml(self, config_dir: Path) -> None:
        (config_dir / "test_customer" / "config.yaml").write_text(": invalid: yaml: [")
        with pytest.raises(Exception):
            load_config(str(config_dir), "test_customer")

    def test_invalid_config_schema(self, config_dir: Path) -> None:
        """Config that doesn't match Pydantic schema."""
        config_yaml = {"customer": {"customer_id": "test"}}  # missing customer_name and warehouse
        (config_dir / "test_customer" / "config.yaml").write_text(yaml.dump(config_yaml))
        with pytest.raises(Exception):
            load_config(str(config_dir), "test_customer")
