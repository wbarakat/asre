"""E2E warehouse adapter conformance test suite.

Runs the same tests against Postgres (real), BigQuery (emulator), and
Redshift (redshift-connector against Postgres). Each test receives the
parametrized ``adapter`` fixture from conftest.py.

Adapters that are unavailable are skipped gracefully.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from asre.ingest.base import IngestAdapter
from asre.migration.migrator import Migrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_table(prefix: str = "conformance") -> str:
    """Generate a unique table name to avoid cross-test collisions."""
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix}_{suffix}"


def _text_type(adapter: IngestAdapter) -> str:
    """Return the correct text column type for this adapter."""
    wt = adapter.warehouse_type
    if wt == "bigquery":
        return "STRING"
    if wt == "redshift":
        return "VARCHAR(65535)"
    return "TEXT"


def _qualify(adapter: IngestAdapter, table: str) -> str:
    """Qualify a table name with dataset/schema when needed.

    BigQuery requires dataset.table; Postgres and Redshift work unqualified
    (schema is set at connection level).
    """
    if adapter.warehouse_type == "bigquery":
        dataset = getattr(adapter, "_dataset", "test") or "test"
        return f"{dataset}.{table}"
    return table


def _create_test_table(adapter: IngestAdapter, table: str, extra_cols: str = "") -> None:
    """Create a simple test table with warehouse-appropriate DDL."""
    t = _text_type(adapter)
    qualified = _qualify(adapter, table)
    cols = f"id {t} NOT NULL, name {t}, value {t}"
    if extra_cols:
        cols += f", {extra_cols}"
    adapter.execute_ddl(f"CREATE TABLE {qualified} ({cols})")


def _drop_table(adapter: IngestAdapter, table: str) -> None:
    """Drop a table, ignoring errors if it doesn't exist."""
    qualified = _qualify(adapter, table)
    try:
        adapter.execute_ddl(f"DROP TABLE IF EXISTS {qualified}")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------

class TestAdapterLifecycle:
    """Basic adapter lifecycle checks."""

    def test_warehouse_type_returns_valid_string(self, adapter: IngestAdapter) -> None:
        assert adapter.warehouse_type in {"postgres", "bigquery", "redshift"}

    def test_adapter_is_connected(self, adapter: IngestAdapter) -> None:
        """After fixture setup, adapter should be usable for queries."""
        # A trivial query that works on all warehouses
        if adapter.warehouse_type == "bigquery":
            rows = adapter.read_source("ping", "SELECT 1 AS n")
        else:
            rows = adapter.read_source("ping", "SELECT 1 AS n")
        assert len(rows) == 1
        assert rows[0]["n"] == 1


class TestAdapterDDL:
    """CREATE TABLE and DROP TABLE conformance."""

    def test_create_and_drop_table(self, adapter: IngestAdapter) -> None:
        table = _unique_table("ddl")
        _create_test_table(adapter, table)
        _drop_table(adapter, table)

    def test_drop_if_exists_is_idempotent(self, adapter: IngestAdapter) -> None:
        table = _unique_table("ddl_idem")
        # Table doesn't exist — should not error
        _drop_table(adapter, table)
        # Create then drop twice
        _create_test_table(adapter, table)
        _drop_table(adapter, table)
        _drop_table(adapter, table)


class TestWriteReadRoundTrip:
    """write_records + read_source round-trip conformance."""

    def test_write_and_read_records(self, adapter: IngestAdapter) -> None:
        table = _unique_table("wr")
        _create_test_table(adapter, table)
        try:
            records = [
                {"id": "1", "name": "Alice", "value": "100"},
                {"id": "2", "name": "Bob", "value": "200"},
            ]
            written = adapter.write_records(table, records)
            assert written == 2

            qualified = _qualify(adapter, table)
            rows = adapter.read_source("test", f"SELECT id, name, value FROM {qualified} ORDER BY id")
            assert len(rows) == 2
            assert rows[0]["id"] == "1"
            assert rows[0]["name"] == "Alice"
            assert rows[1]["id"] == "2"
            assert rows[1]["name"] == "Bob"
        finally:
            _drop_table(adapter, table)

    def test_write_empty_list_returns_zero(self, adapter: IngestAdapter) -> None:
        table = _unique_table("wr_empty")
        _create_test_table(adapter, table)
        try:
            assert adapter.write_records(table, []) == 0
        finally:
            _drop_table(adapter, table)

    def test_null_values_round_trip(self, adapter: IngestAdapter) -> None:
        table = _unique_table("wr_null")
        _create_test_table(adapter, table)
        try:
            records = [{"id": "1", "name": None, "value": None}]
            adapter.write_records(table, records)

            qualified = _qualify(adapter, table)
            rows = adapter.read_source("test", f"SELECT id, name, value FROM {qualified}")
            assert len(rows) == 1
            assert rows[0]["id"] == "1"
            assert rows[0]["name"] is None
            assert rows[0]["value"] is None
        finally:
            _drop_table(adapter, table)


class TestAdapterDML:
    """execute_dml conformance for UPDATE and DELETE."""

    def test_update_with_params(self, adapter: IngestAdapter) -> None:
        table = _unique_table("dml_upd")
        _create_test_table(adapter, table)
        try:
            adapter.write_records(table, [
                {"id": "1", "name": "Alice", "value": "old"},
            ])

            qualified = _qualify(adapter, table)
            adapter.execute_dml(
                f"UPDATE {qualified} SET value = :new_val WHERE id = :id",
                {"new_val": "new", "id": "1"},
            )

            rows = adapter.read_source("test", f"SELECT value FROM {qualified} WHERE id = '1'")
            assert len(rows) == 1
            assert rows[0]["value"] == "new"
        finally:
            _drop_table(adapter, table)

    def test_delete_with_params(self, adapter: IngestAdapter) -> None:
        table = _unique_table("dml_del")
        _create_test_table(adapter, table)
        try:
            adapter.write_records(table, [
                {"id": "1", "name": "Alice", "value": "x"},
                {"id": "2", "name": "Bob", "value": "y"},
            ])

            qualified = _qualify(adapter, table)
            adapter.execute_dml(
                f"DELETE FROM {qualified} WHERE id = :id",
                {"id": "1"},
            )

            rows = adapter.read_source("test", f"SELECT id FROM {qualified} ORDER BY id")
            assert len(rows) == 1
            assert rows[0]["id"] == "2"
        finally:
            _drop_table(adapter, table)


class TestWatermarkConformance:
    """Watermark get/set conformance across warehouses."""

    @pytest.fixture(autouse=True)
    def _metadata_table(self, adapter: IngestAdapter) -> Any:
        """Ensure asre_metadata exists and is clean before each test."""
        from asre.migration.ddl_types import DDLTypeMapper

        wt = adapter.warehouse_type
        m = DDLTypeMapper(wt)

        qualified = _qualify(adapter, "asre_metadata")
        try:
            adapter.execute_ddl(f"DROP TABLE IF EXISTS {qualified}")
        except Exception:
            pass

        key_col = m.primary_key("key")
        value_type = m.text()
        adapter.execute_ddl(
            f"CREATE TABLE {qualified} ({key_col}, value {value_type} NOT NULL)"
        )
        yield
        try:
            adapter.execute_ddl(f"DROP TABLE IF EXISTS {qualified}")
        except Exception:
            pass

    def test_get_watermark_returns_none_initially(self, adapter: IngestAdapter) -> None:
        result = adapter.get_watermark("nonexistent_source")
        assert result is None

    def test_set_and_get_watermark_round_trip(self, adapter: IngestAdapter) -> None:
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        adapter.set_watermark("adt_vendor_x", ts)
        result = adapter.get_watermark("adt_vendor_x")
        assert result is not None
        assert result == ts

    def test_watermarks_are_per_source(self, adapter: IngestAdapter) -> None:
        ts_a = datetime(2026, 1, 10, 8, 0, 0, tzinfo=timezone.utc)
        ts_b = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)
        adapter.set_watermark("source_a", ts_a)
        adapter.set_watermark("source_b", ts_b)
        assert adapter.get_watermark("source_a") == ts_a
        assert adapter.get_watermark("source_b") == ts_b

    def test_set_watermark_upsert_overwrites(self, adapter: IngestAdapter) -> None:
        ts1 = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        adapter.set_watermark("src", ts1)
        assert adapter.get_watermark("src") == ts1
        adapter.set_watermark("src", ts2)
        assert adapter.get_watermark("src") == ts2


class TestMigrationConformance:
    """Migrator.run() conformance across warehouses.

    Skipped for Redshift-on-Postgres because migrations emit Redshift-specific
    DDL types (SUPER, VARCHAR(65535) with PRIMARY KEY) that vanilla PG rejects.
    """

    @pytest.fixture(autouse=True)
    def _skip_redshift_on_postgres(self, adapter: IngestAdapter) -> None:
        if adapter.warehouse_type == "redshift":
            pytest.skip("Migration DDL uses Redshift-specific types (SUPER) unsupported by Postgres")

    @pytest.fixture(autouse=True)
    def _clean_slate(self, adapter: IngestAdapter) -> Any:
        """Drop all ASRE tables before and after each test."""
        tables = [
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
        for t in tables:
            qualified = _qualify(adapter, t)
            try:
                adapter.execute_ddl(f"DROP TABLE IF EXISTS {qualified}")
            except Exception:
                pass
        yield
        for t in tables:
            qualified = _qualify(adapter, t)
            try:
                adapter.execute_ddl(f"DROP TABLE IF EXISTS {qualified}")
            except Exception:
                pass

    def test_migrator_creates_all_tables(self, adapter: IngestAdapter) -> None:
        migrator = Migrator(adapter)
        result = migrator.run()
        assert result.applied > 0
        assert result.current_version > 0

        # Verify schema_version was recorded
        version = migrator.get_schema_version()
        assert version == result.current_version

    def test_migrator_is_idempotent(self, adapter: IngestAdapter) -> None:
        migrator = Migrator(adapter)
        result1 = migrator.run()
        assert result1.applied > 0

        result2 = migrator.run()
        assert result2.applied == 0
        assert result2.current_version == result1.current_version

    def test_migrator_creates_nine_tables(self, adapter: IngestAdapter) -> None:
        migrator = Migrator(adapter)
        migrator.run()

        # Verify all 9 tables are queryable
        expected_tables = [
            "asre_metadata",
            "admission_events_unified",
            "asre_encounters_detail",
            "asre_audit_log",
            "asre_run_metrics",
            "asre_quality_metrics",
            "asre_episodes",
            "asre_canonical_events",
            "asre_facility_registry",
        ]
        for table in expected_tables:
            qualified = _qualify(adapter, table)
            rows = adapter.read_source("check", f"SELECT COUNT(*) AS cnt FROM {qualified}")
            # asre_metadata has 1 row (schema_version); all others should be empty
            if table == "asre_metadata":
                assert rows[0]["cnt"] == 1, "asre_metadata should have schema_version row"
            else:
                assert rows[0]["cnt"] == 0, f"Table {table} should be empty after migration"
