"""Tests for US-100: Handle cross-warehouse dbt compatibility.

Verifies that dbt profiles, macros, and models support Snowflake,
BigQuery, and Redshift in addition to Postgres.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DBT_PROJECT_DIR = Path(__file__).parent.parent.parent / "dbt_project"


def _load_profiles() -> dict[str, Any]:
    """Load and parse profiles.yml."""
    with open(DBT_PROJECT_DIR / "profiles.yml") as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def _load_dbt_project() -> dict[str, Any]:
    """Load and parse dbt_project.yml."""
    with open(DBT_PROJECT_DIR / "dbt_project.yml") as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


class TestProfiles:
    """Verify dbt profiles exist for all three warehouses plus Postgres."""

    def test_profiles_yml_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "profiles.yml").is_file()

    def test_has_postgres_profile(self) -> None:
        profiles = _load_profiles()
        outputs = profiles["asre"]["outputs"]
        assert "dev" in outputs
        assert outputs["dev"]["type"] == "postgres"

    def test_has_snowflake_profile(self) -> None:
        profiles = _load_profiles()
        outputs = profiles["asre"]["outputs"]
        assert "snowflake" in outputs
        assert outputs["snowflake"]["type"] == "snowflake"

    def test_has_bigquery_profile(self) -> None:
        profiles = _load_profiles()
        outputs = profiles["asre"]["outputs"]
        assert "bigquery" in outputs
        assert outputs["bigquery"]["type"] == "bigquery"

    def test_has_redshift_profile(self) -> None:
        profiles = _load_profiles()
        outputs = profiles["asre"]["outputs"]
        assert "redshift" in outputs
        assert outputs["redshift"]["type"] == "redshift"

    def test_snowflake_profile_has_required_fields(self) -> None:
        profiles = _load_profiles()
        sf = profiles["asre"]["outputs"]["snowflake"]
        required_fields = ["account", "user", "password", "warehouse", "database", "schema"]
        for field in required_fields:
            assert field in sf, f"Snowflake profile missing '{field}'"

    def test_bigquery_profile_has_required_fields(self) -> None:
        profiles = _load_profiles()
        bq = profiles["asre"]["outputs"]["bigquery"]
        required_fields = ["project", "dataset", "method"]
        for field in required_fields:
            assert field in bq, f"BigQuery profile missing '{field}'"

    def test_redshift_profile_has_required_fields(self) -> None:
        profiles = _load_profiles()
        rs = profiles["asre"]["outputs"]["redshift"]
        required_fields = ["host", "port", "user", "password", "dbname", "schema"]
        for field in required_fields:
            assert field in rs, f"Redshift profile missing '{field}'"


class TestMacros:
    """Verify cross-warehouse macros exist and cover key SQL differences."""

    def test_macros_directory_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "macros").is_dir()

    def test_cross_warehouse_macros_file_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").is_file()

    def test_macros_referenced_in_dbt_project(self) -> None:
        config = _load_dbt_project()
        assert "macros" in config.get("macro-paths", [])

    def test_json_type_macro_defined(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        assert "macro json_type()" in macro_content

    def test_array_type_macro_defined(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        assert "macro array_type()" in macro_content

    def test_timestamp_type_macro_defined(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        assert "macro timestamp_type()" in macro_content

    def test_quote_identifier_macro_defined(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        assert "macro quote_identifier(" in macro_content

    def test_json_type_macro_covers_all_warehouses(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        assert "VARIANT" in macro_content  # Snowflake
        assert "SUPER" in macro_content  # Redshift
        assert "JSONB" in macro_content  # Postgres

    def test_timestamp_type_macro_covers_all_warehouses(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        assert "TIMESTAMP_TZ" in macro_content  # Snowflake
        assert "TIMESTAMPTZ" in macro_content  # Postgres/Redshift

    def test_quote_identifier_handles_bigquery(self) -> None:
        macro_content = (DBT_PROJECT_DIR / "macros" / "cross_warehouse.sql").read_text()
        # BigQuery uses backticks for quoting
        assert "bigquery" in macro_content
        assert "`" in macro_content


class TestModelCompatibility:
    """Verify models use cross-warehouse compatible SQL."""

    MART_MODELS = [
        "admission_events_unified.sql",
        "asre_encounters_detail.sql",
        "asre_audit_log.sql",
        "asre_run_metrics.sql",
        "asre_quality_metrics.sql",
        "asre_episodes.sql",
    ]

    def test_all_mart_models_exist(self) -> None:
        marts_dir = DBT_PROJECT_DIR / "models" / "marts"
        for model in self.MART_MODELS:
            assert (marts_dir / model).is_file(), f"Missing mart model: {model}"

    def test_incremental_models_have_unique_key(self) -> None:
        """Incremental models must use unique_key for merge compatibility."""
        marts_dir = DBT_PROJECT_DIR / "models" / "marts"
        incremental_models = [
            "admission_events_unified.sql",
            "asre_episodes.sql",
        ]
        for model_name in incremental_models:
            content = (marts_dir / model_name).read_text()
            assert "unique_key" in content, (
                f"{model_name} must use unique_key for cross-warehouse merge"
            )

    def test_audit_log_quotes_timestamp(self) -> None:
        """The 'timestamp' column is a reserved word and must be quoted."""
        content = (
            DBT_PROJECT_DIR / "models" / "marts" / "asre_audit_log.sql"
        ).read_text()
        assert "quote_identifier" in content, (
            "asre_audit_log.sql must use quote_identifier for 'timestamp' column"
        )

    def test_models_use_source_macro(self) -> None:
        """All models should use {{ source() }} macro for cross-warehouse table refs."""
        marts_dir = DBT_PROJECT_DIR / "models" / "marts"
        for model_name in self.MART_MODELS:
            content = (marts_dir / model_name).read_text()
            assert "source(" in content, (
                f"{model_name} must use source() macro for table references"
            )

    def test_no_warehouse_specific_functions_in_models(self) -> None:
        """Models should not use warehouse-specific SQL functions directly."""
        marts_dir = DBT_PROJECT_DIR / "models" / "marts"
        warehouse_specific = [
            "PARSE_JSON",  # Snowflake-specific
            "TO_VARIANT",  # Snowflake-specific
            "JSON_EXTRACT",  # BigQuery-specific
            "JSON_EXTRACT_PATH_TEXT",  # Redshift-specific
        ]
        for model_name in self.MART_MODELS:
            content = (marts_dir / model_name).read_text().upper()
            for func in warehouse_specific:
                assert func not in content, (
                    f"{model_name} contains warehouse-specific function '{func}'"
                )


class TestSourcesCompatibility:
    """Verify sources are configured for cross-warehouse use."""

    def test_sources_yml_exists(self) -> None:
        assert (DBT_PROJECT_DIR / "models" / "staging" / "sources.yml").is_file()

    def test_source_schema_is_configurable(self) -> None:
        """Source schema should use var() or target.schema for portability."""
        content = (
            DBT_PROJECT_DIR / "models" / "staging" / "sources.yml"
        ).read_text()
        # Should NOT have hardcoded 'public' schema
        assert "var(" in content or "target.schema" in content, (
            "Source schema must be configurable via var() or target.schema"
        )
