"""Unit tests for migration 001_initial_schema (v1.0.0 consolidated schema).

Verifies that the migration creates all 9 tables:
asre_metadata, admission_events_unified, asre_encounters_detail,
asre_audit_log, asre_run_metrics, asre_quality_metrics, asre_episodes,
asre_canonical_events, asre_facility_registry.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from asre.migration.versions import _001_initial_schema as migration


class TestInitialSchemaMigration:
    """Tests for 001_initial_schema migration script."""

    def test_has_upgrade_function(self) -> None:
        """Migration module has an upgrade function."""
        assert callable(migration.upgrade)

    def test_has_description(self) -> None:
        """Migration module has a description string."""
        assert hasattr(migration, "description")
        assert isinstance(migration.description, str)
        assert len(migration.description) > 0

    def test_upgrade_creates_all_nine_tables(self) -> None:
        """upgrade() calls execute_ddl 9 times (one per table)."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        assert adapter.execute_ddl.call_count == 9

    def test_creates_asre_metadata(self) -> None:
        """upgrade() creates asre_metadata table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_metadata")
        assert ddl is not None, "DDL for asre_metadata not found"
        assert "key" in ddl
        assert "value" in ddl

    def test_creates_admission_events_unified(self) -> None:
        """upgrade() creates admission_events_unified with key columns."""
        adapter = MagicMock()
        migration.upgrade(adapter)

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

    def test_creates_asre_encounters_detail(self) -> None:
        """upgrade() creates asre_encounters_detail table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_encounters_detail")
        assert ddl is not None, "DDL for asre_encounters_detail not found"

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

    def test_creates_asre_audit_log(self) -> None:
        """upgrade() creates asre_audit_log table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_audit_log")
        assert ddl is not None, "DDL for asre_audit_log not found"

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

    def test_creates_asre_run_metrics(self) -> None:
        """upgrade() creates asre_run_metrics table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_run_metrics")
        assert ddl is not None, "DDL for asre_run_metrics not found"

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

    def test_creates_asre_quality_metrics(self) -> None:
        """upgrade() creates asre_quality_metrics with _009 columns."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_quality_metrics")
        assert ddl is not None, "DDL for asre_quality_metrics not found"

        required_columns = [
            "run_id",
            "metric_name",
            "metric_value",
            "warn_threshold",
            "fail_threshold",
            "status",
            "computed_at",
            "metric_id",
            "detail",
            "run_ts",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_quality_metrics DDL"

    def test_creates_asre_episodes(self) -> None:
        """upgrade() creates asre_episodes table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_episodes")
        assert ddl is not None, "DDL for asre_episodes not found"

        required_columns = [
            "episode_id",
            "patient_key",
            "episode_type",
            "episode_status",
            "episode_start_ts",
            "episode_end_ts",
            "total_los_days",
            "encounter_ids",
            "encounter_count",
            "facility_count",
            "facility_sequence",
            "includes_readmission",
            "includes_post_acute",
            "is_acute",
            "principal_diagnosis",
            "diagnosis_codes",
            "confidence_score",
            "created_at",
            "updated_at",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_episodes DDL"

    def test_creates_asre_canonical_events(self) -> None:
        """upgrade() creates asre_canonical_events with admitting_diagnosis."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_canonical_events")
        assert ddl is not None, "DDL for asre_canonical_events not found"

        required_columns = [
            "event_id",
            "patient_key",
            "event_type",
            "event_ts",
            "source_system",
            "source_record_id",
            "facility_raw",
            "facility_canonical_id",
            "facility_match_type",
            "npi",
            "ccn",
            "admit_flag",
            "discharge_flag",
            "auth_flag",
            "patient_class",
            "drg",
            "principal_diagnosis",
            "diagnosis_codes",
            "auth_status",
            "payer_id",
            "ingested_at",
            "batch_id",
            "raw_payload",
            "admitting_diagnosis",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_canonical_events DDL"

    def test_creates_asre_facility_registry(self) -> None:
        """upgrade() creates asre_facility_registry with address column."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl = _find_ddl_for_table(adapter, "asre_facility_registry")
        assert ddl is not None, "DDL for asre_facility_registry not found"

        required_columns = [
            "canonical_id",
            "canonical_name",
            "npi",
            "ccn",
            "facility_type",
            "aliases",
            "flags",
            "address",
        ]
        for col in required_columns:
            assert col in ddl, f"Missing column {col} in asre_facility_registry DDL"

    def test_uses_if_not_exists(self) -> None:
        """All CREATE TABLE DDL uses IF NOT EXISTS for idempotency."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        for call_args in adapter.execute_ddl.call_args_list:
            ddl = call_args[0][0]
            assert "IF NOT EXISTS" in ddl, f"Missing IF NOT EXISTS in: {ddl[:80]}"

    def test_upgrade_is_idempotent(self) -> None:
        """Running upgrade twice does not error (IF NOT EXISTS)."""
        adapter = MagicMock()
        migration.upgrade(adapter)
        migration.upgrade(adapter)

        # 18 total calls (9 per run)
        assert adapter.execute_ddl.call_count == 18

    def test_downgrade_drops_all_tables(self) -> None:
        """downgrade() drops all 9 tables."""
        adapter = MagicMock()
        migration.downgrade(adapter)

        assert adapter.execute_ddl.call_count == 9

        ddl_calls = [c[0][0] for c in adapter.execute_ddl.call_args_list]
        expected_tables = [
            "asre_facility_registry",
            "asre_canonical_events",
            "asre_episodes",
            "asre_quality_metrics",
            "asre_run_metrics",
            "asre_audit_log",
            "asre_encounters_detail",
            "admission_events_unified",
            "asre_metadata",
        ]
        for table in expected_tables:
            assert any(
                table in ddl and "DROP TABLE" in ddl for ddl in ddl_calls
            ), f"Missing DROP TABLE for {table}"


def _find_ddl_for_table(adapter: MagicMock, table_name: str) -> str | None:
    """Find the DDL call that creates a specific table."""
    for call_args in adapter.execute_ddl.call_args_list:
        ddl: str = call_args[0][0]
        if table_name in ddl and "CREATE TABLE" in ddl:
            return ddl
    return None
