"""Unit tests for migration 003_output_tables (US-080).

Verifies that the migration creates all 5 output tables:
admission_events_unified, asre_encounters_detail, asre_audit_log,
asre_run_metrics, asre_quality_metrics.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

import pytest


class TestOutputTablesMigration:
    """Tests for 003_output_tables migration script."""

    def test_migration_module_exists(self) -> None:
        """Migration module can be imported."""
        from asre.migration.versions import _003_output_tables  # noqa: F401

    def test_migration_has_description(self) -> None:
        """Migration module has a description attribute."""
        from asre.migration.versions import _003_output_tables

        assert hasattr(_003_output_tables, "description")
        assert isinstance(_003_output_tables.description, str)
        assert len(_003_output_tables.description) > 0

    def test_migration_has_upgrade_function(self) -> None:
        """Migration module has an upgrade function."""
        from asre.migration.versions import _003_output_tables

        assert callable(_003_output_tables.upgrade)

    def test_upgrade_creates_five_tables(self) -> None:
        """upgrade() calls execute_ddl for each of the 5 output tables."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        # Should have been called 5 times (one per table)
        assert adapter.execute_ddl.call_count == 5

    def test_creates_admission_events_unified(self) -> None:
        """upgrade() creates admission_events_unified table."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        ddl_combined = " ".join(ddl_calls)
        assert "admission_events_unified" in ddl_combined

    def test_creates_asre_encounters_detail(self) -> None:
        """upgrade() creates asre_encounters_detail table."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        ddl_combined = " ".join(ddl_calls)
        assert "asre_encounters_detail" in ddl_combined

    def test_creates_asre_audit_log(self) -> None:
        """upgrade() creates asre_audit_log table."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        ddl_combined = " ".join(ddl_calls)
        assert "asre_audit_log" in ddl_combined

    def test_creates_asre_run_metrics(self) -> None:
        """upgrade() creates asre_run_metrics table."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        ddl_combined = " ".join(ddl_calls)
        assert "asre_run_metrics" in ddl_combined

    def test_creates_asre_quality_metrics(self) -> None:
        """upgrade() creates asre_quality_metrics table."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        ddl_combined = " ".join(ddl_calls)
        assert "asre_quality_metrics" in ddl_combined

    def test_uses_if_not_exists(self) -> None:
        """All DDL uses IF NOT EXISTS for idempotency."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        for call_args in adapter.execute_ddl.call_args_list:
            ddl = call_args[0][0]
            assert "IF NOT EXISTS" in ddl, f"Missing IF NOT EXISTS in: {ddl[:80]}"

    def test_admission_events_unified_columns(self) -> None:
        """admission_events_unified has all required columns from SPEC."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        # Find the DDL for admission_events_unified
        ddl = _find_ddl_for_table(adapter, "admission_events_unified")
        assert ddl is not None, "DDL for admission_events_unified not found"

        required_columns = [
            "encounter_id",
            "patient_key",
            "encounter_type",
            "status",
            "admit_ts",
            "discharge_ts",
            "los_hours",
            "facility_canonical_id",
            "facility_name",
            "is_acute",
            "source_event_ids",
            "source_systems",
            "has_adt",
            "has_claims",
            "has_auth",
            "confidence_score",
            "confidence_flags",
            "admit_source_priority",
            "discharge_source_priority",
            "payer_id",
            "drg",
            "principal_diagnosis",
            "admitting_diagnosis",
            "diagnosis_codes",
            "is_readmission",
            "readmission_days",
            "obs_to_ip_conversion",
            "transfer_chain",
            "episode_id",
            "created_at",
            "updated_at",
            "asre_version",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in admission_events_unified DDL"

    def test_admission_events_unified_primary_key(self) -> None:
        """admission_events_unified has encounter_id as PRIMARY KEY."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "admission_events_unified")
        assert ddl is not None
        assert "encounter_id" in ddl
        assert "PRIMARY KEY" in ddl

    def test_asre_encounters_detail_columns(self) -> None:
        """asre_encounters_detail has required columns."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_encounters_detail")
        assert ddl is not None

        required_columns = [
            "encounter_id",
            "event_id",
            "event_type",
            "event_ts",
            "source_system",
            "role_in_encounter",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_encounters_detail DDL"

    def test_asre_audit_log_columns(self) -> None:
        """asre_audit_log has required columns."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_audit_log")
        assert ddl is not None

        required_columns = [
            "log_id",
            "run_id",
            "timestamp",
            "action",
            "entity_type",
            "entity_id",
            "detail",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_audit_log DDL"

    def test_asre_run_metrics_columns(self) -> None:
        """asre_run_metrics has required columns."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_run_metrics")
        assert ddl is not None

        required_columns = [
            "run_id",
            "stage_name",
            "started_at",
            "completed_at",
            "records_in",
            "records_out",
            "errors",
            "status",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_run_metrics DDL"

    def test_asre_quality_metrics_columns(self) -> None:
        """asre_quality_metrics has required columns."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        _003_output_tables.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_quality_metrics")
        assert ddl is not None

        required_columns = [
            "run_id",
            "metric_name",
            "metric_value",
            "warn_threshold",
            "fail_threshold",
            "status",
            "computed_at",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_quality_metrics DDL"

    def test_migration_is_idempotent(self) -> None:
        """Running upgrade twice does not error (IF NOT EXISTS)."""
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        # Should not raise on first or second call
        _003_output_tables.upgrade(adapter)
        _003_output_tables.upgrade(adapter)

        # 10 total calls (5 per run)
        assert adapter.execute_ddl.call_count == 10

    def test_migrator_discovers_003(self) -> None:
        """Migrator discovers 003_output_tables migration."""
        from asre.migration.migrator import Migrator

        adapter = MagicMock()
        migrator = Migrator(adapter)
        migrations = migrator.discover_migrations()

        versions = [m.version for m in migrations]
        assert 3 in versions


def _find_ddl_for_table(adapter: MagicMock, table_name: str) -> str | None:
    """Find the DDL call that creates a specific table."""
    for call_args in adapter.execute_ddl.call_args_list:
        ddl: str = call_args[0][0]
        if table_name in ddl and "CREATE TABLE" in ddl:
            return ddl
    return None
