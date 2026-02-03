"""Tests for US-084: Implement dbt schema tests.

Verifies that dbt schema YAML files define the required tests for
output table integrity.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DBT_PROJECT_DIR = Path(__file__).parent.parent.parent / "dbt_project"
SCHEMA_PATH = DBT_PROJECT_DIR / "models" / "marts" / "schema.yml"


def _load_schema() -> dict[str, Any]:
    """Load and parse the marts schema.yml."""
    with open(SCHEMA_PATH) as f:
        result: dict[str, Any] = yaml.safe_load(f)
        return result


def _get_model(schema: dict[str, Any], model_name: str) -> dict[str, Any]:
    """Find a model definition by name."""
    for model in schema["models"]:
        if model["name"] == model_name:
            result: dict[str, Any] = model
            return result
    raise AssertionError(f"Model '{model_name}' not found in schema.yml")


def _get_column(model: dict[str, Any], column_name: str) -> dict[str, Any]:
    """Find a column definition by name within a model."""
    for col in model.get("columns", []):
        if col["name"] == column_name:
            result: dict[str, Any] = col
            return result
    raise AssertionError(
        f"Column '{column_name}' not found in model '{model['name']}'"
    )


def _column_has_test(column: dict[str, Any], test_name: str) -> bool:
    """Check if a column has a specific test defined."""
    for test in column.get("tests", []):
        if isinstance(test, str) and test == test_name:
            return True
        if isinstance(test, dict) and test_name in test:
            return True
    return False


def _get_test_config(column: dict[str, Any], test_name: str) -> dict[str, Any] | None:
    """Get the configuration dict for a specific test on a column."""
    for test in column.get("tests", []):
        if isinstance(test, dict) and test_name in test:
            result: dict[str, Any] = test[test_name]
            return result
    return None


class TestSchemaFileExists:
    """Verify schema.yml exists and is valid YAML."""

    def test_schema_yml_exists(self) -> None:
        assert SCHEMA_PATH.is_file(), "models/marts/schema.yml must exist"

    def test_schema_yml_is_valid_yaml(self) -> None:
        schema = _load_schema()
        assert schema is not None
        assert "version" in schema
        assert schema["version"] == 2

    def test_schema_yml_has_models(self) -> None:
        schema = _load_schema()
        assert "models" in schema
        assert len(schema["models"]) > 0


class TestAdmissionEventsUnifiedTests:
    """Verify admission_events_unified has required dbt tests."""

    def test_model_exists_in_schema(self) -> None:
        schema = _load_schema()
        _get_model(schema, "admission_events_unified")

    def test_encounter_id_unique(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "admission_events_unified")
        col = _get_column(model, "encounter_id")
        assert _column_has_test(col, "unique"), (
            "encounter_id must have 'unique' test"
        )

    def test_encounter_id_not_null(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "admission_events_unified")
        col = _get_column(model, "encounter_id")
        assert _column_has_test(col, "not_null"), (
            "encounter_id must have 'not_null' test"
        )

    def test_patient_key_not_null(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "admission_events_unified")
        col = _get_column(model, "patient_key")
        assert _column_has_test(col, "not_null"), (
            "patient_key must have 'not_null' test"
        )

    def test_admit_ts_not_null(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "admission_events_unified")
        col = _get_column(model, "admit_ts")
        assert _column_has_test(col, "not_null"), (
            "admit_ts must have 'not_null' test"
        )

    def test_status_accepted_values(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "admission_events_unified")
        col = _get_column(model, "status")
        assert _column_has_test(col, "accepted_values"), (
            "status must have 'accepted_values' test"
        )
        config = _get_test_config(col, "accepted_values")
        assert config is not None
        assert set(config["values"]) == {"open", "closed", "cancelled"}

    def test_encounter_type_accepted_values(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "admission_events_unified")
        col = _get_column(model, "encounter_type")
        assert _column_has_test(col, "accepted_values"), (
            "encounter_type must have 'accepted_values' test"
        )
        config = _get_test_config(col, "accepted_values")
        assert config is not None
        assert set(config["values"]) == {
            "inpatient", "observation", "ed_only", "outpatient"
        }


class TestEncountersDetailTests:
    """Verify asre_encounters_detail has required dbt tests."""

    def test_model_exists_in_schema(self) -> None:
        schema = _load_schema()
        _get_model(schema, "asre_encounters_detail")

    def test_encounter_id_not_null(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "asre_encounters_detail")
        col = _get_column(model, "encounter_id")
        assert _column_has_test(col, "not_null"), (
            "encounter_id must have 'not_null' test"
        )

    def test_encounter_id_relationships(self) -> None:
        schema = _load_schema()
        model = _get_model(schema, "asre_encounters_detail")
        col = _get_column(model, "encounter_id")
        assert _column_has_test(col, "relationships"), (
            "encounter_id must have 'relationships' test"
        )
        config = _get_test_config(col, "relationships")
        assert config is not None
        assert config["to"] == "ref('admission_events_unified')"
        assert config["field"] == "encounter_id"
