"""Tests for cross-warehouse migration support (US-101).

Verifies that migration scripts detect warehouse type from the adapter
and generate warehouse-appropriate DDL syntax.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, call

import pytest

from asre.migration.ddl_types import DDLTypeMapper


class TestDDLTypeMapper:
    """Test DDL type mapping across warehouses."""

    def test_postgres_text_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.text() == "TEXT"

    def test_postgres_boolean_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.boolean() == "BOOLEAN"

    def test_postgres_integer_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.integer() == "INTEGER"

    def test_postgres_real_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.real() == "REAL"

    def test_postgres_json_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.json() == "JSONB"

    def test_postgres_array_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.array() == "JSONB"

    def test_postgres_timestamp_type(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.timestamp() == "TIMESTAMPTZ"

    # -- Snowflake --

    def test_snowflake_text_type(self) -> None:
        mapper = DDLTypeMapper("snowflake")
        assert mapper.text() == "TEXT"

    def test_snowflake_boolean_type(self) -> None:
        mapper = DDLTypeMapper("snowflake")
        assert mapper.boolean() == "BOOLEAN"

    def test_snowflake_json_type(self) -> None:
        mapper = DDLTypeMapper("snowflake")
        assert mapper.json() == "VARIANT"

    def test_snowflake_array_type(self) -> None:
        mapper = DDLTypeMapper("snowflake")
        assert mapper.array() == "ARRAY"

    def test_snowflake_timestamp_type(self) -> None:
        mapper = DDLTypeMapper("snowflake")
        assert mapper.timestamp() == "TIMESTAMP_TZ"

    # -- BigQuery --

    def test_bigquery_text_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.text() == "STRING"

    def test_bigquery_boolean_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.boolean() == "BOOL"

    def test_bigquery_integer_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.integer() == "INT64"

    def test_bigquery_real_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.real() == "FLOAT64"

    def test_bigquery_json_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.json() == "JSON"

    def test_bigquery_array_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.array() == "JSON"

    def test_bigquery_timestamp_type(self) -> None:
        mapper = DDLTypeMapper("bigquery")
        assert mapper.timestamp() == "TIMESTAMP"

    # -- Redshift --

    def test_redshift_text_type(self) -> None:
        mapper = DDLTypeMapper("redshift")
        assert mapper.text() == "VARCHAR(65535)"

    def test_redshift_boolean_type(self) -> None:
        mapper = DDLTypeMapper("redshift")
        assert mapper.boolean() == "BOOLEAN"

    def test_redshift_json_type(self) -> None:
        mapper = DDLTypeMapper("redshift")
        assert mapper.json() == "SUPER"

    def test_redshift_array_type(self) -> None:
        mapper = DDLTypeMapper("redshift")
        assert mapper.array() == "SUPER"

    def test_redshift_timestamp_type(self) -> None:
        mapper = DDLTypeMapper("redshift")
        assert mapper.timestamp() == "TIMESTAMPTZ"

    # -- Unknown warehouse --

    def test_unknown_warehouse_defaults_to_postgres(self) -> None:
        mapper = DDLTypeMapper("unknown")
        assert mapper.text() == "TEXT"
        assert mapper.boolean() == "BOOLEAN"


class TestDDLTypeMapperPrimaryKey:
    """Test primary key DDL generation across warehouses."""

    def test_postgres_primary_key(self) -> None:
        mapper = DDLTypeMapper("postgres")
        assert mapper.primary_key("id") == "id TEXT PRIMARY KEY"

    def test_snowflake_primary_key(self) -> None:
        mapper = DDLTypeMapper("snowflake")
        assert mapper.primary_key("id") == "id TEXT PRIMARY KEY"

    def test_bigquery_primary_key_no_constraint(self) -> None:
        """BigQuery doesn't support PRIMARY KEY constraint in CREATE TABLE."""
        mapper = DDLTypeMapper("bigquery")
        result = mapper.primary_key("id")
        assert result == "id STRING NOT NULL"

    def test_redshift_primary_key(self) -> None:
        mapper = DDLTypeMapper("redshift")
        assert mapper.primary_key("id") == "id VARCHAR(65535) PRIMARY KEY"

    def test_composite_primary_key_postgres(self) -> None:
        mapper = DDLTypeMapper("postgres")
        result = mapper.composite_primary_key(["run_id", "stage_name"])
        assert result == "PRIMARY KEY (run_id, stage_name)"

    def test_composite_primary_key_bigquery(self) -> None:
        """BigQuery doesn't support composite PK constraint."""
        mapper = DDLTypeMapper("bigquery")
        result = mapper.composite_primary_key(["run_id", "stage_name"])
        assert result == ""


class TestAdapterWarehouseType:
    """Test that adapters expose warehouse_type property."""

    def test_postgres_adapter_warehouse_type(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        adapter = PostgresAdapter({"host": "localhost", "port": 5432, "database": "test", "user": "test", "password": "test"})
        assert adapter.warehouse_type == "postgres"

    def test_snowflake_adapter_warehouse_type(self) -> None:
        from asre.ingest.snowflake import SnowflakeAdapter

        adapter = SnowflakeAdapter({"account": "test", "user": "test", "password": "test", "database": "test", "schema": "test", "warehouse": "test"})
        assert adapter.warehouse_type == "snowflake"

    def test_bigquery_adapter_warehouse_type(self) -> None:
        from asre.ingest.bigquery import BigQueryAdapter

        adapter = BigQueryAdapter({"project": "test", "dataset": "test"})
        assert adapter.warehouse_type == "bigquery"

    def test_redshift_adapter_warehouse_type(self) -> None:
        from asre.ingest.redshift import RedshiftAdapter

        adapter = RedshiftAdapter({"host": "localhost", "port": 5439, "database": "test", "user": "test", "password": "test"})
        assert adapter.warehouse_type == "redshift"


class TestMigratorCrossWarehouse:
    """Test that Migrator uses warehouse-appropriate upsert for set_schema_version."""

    def test_set_schema_version_postgres_uses_on_conflict(self) -> None:
        from asre.migration.migrator import Migrator

        adapter = MagicMock()
        adapter.warehouse_type = "postgres"
        migrator = Migrator(adapter)

        migrator.set_schema_version(5)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "ON CONFLICT" in ddl
        assert "schema_version" in ddl
        assert "5" in ddl

    def test_set_schema_version_snowflake_uses_merge(self) -> None:
        from asre.migration.migrator import Migrator

        adapter = MagicMock()
        adapter.warehouse_type = "snowflake"
        migrator = Migrator(adapter)

        migrator.set_schema_version(5)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "MERGE" in ddl
        assert "schema_version" in ddl
        assert "5" in ddl

    def test_set_schema_version_bigquery_uses_merge(self) -> None:
        from asre.migration.migrator import Migrator

        adapter = MagicMock()
        adapter.warehouse_type = "bigquery"
        migrator = Migrator(adapter)

        migrator.set_schema_version(5)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "MERGE" in ddl
        assert "schema_version" in ddl

    def test_set_schema_version_redshift_uses_delete_insert(self) -> None:
        from asre.migration.migrator import Migrator

        adapter = MagicMock()
        adapter.warehouse_type = "redshift"
        migrator = Migrator(adapter)

        migrator.set_schema_version(5)

        # Redshift uses two calls: DELETE + INSERT
        calls = adapter.execute_ddl.call_args_list
        ddl_texts = [c[0][0] for c in calls]
        assert any("DELETE" in d for d in ddl_texts)
        assert any("INSERT" in d for d in ddl_texts)
        assert any("schema_version" in d for d in ddl_texts)


class TestMigrationScriptsDetectWarehouseType:
    """Test that migration scripts use warehouse-appropriate DDL."""

    def test_migration_001_works_with_postgres(self) -> None:
        from asre.migration.versions import _001_initial_schema

        adapter = MagicMock()
        adapter.warehouse_type = "postgres"
        _001_initial_schema.upgrade(adapter)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl
        assert "asre_metadata" in ddl
        assert "TEXT" in ddl

    def test_migration_001_works_with_bigquery(self) -> None:
        from asre.migration.versions import _001_initial_schema

        adapter = MagicMock()
        adapter.warehouse_type = "bigquery"
        _001_initial_schema.upgrade(adapter)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl
        assert "asre_metadata" in ddl
        assert "STRING" in ddl

    def test_migration_001_works_with_redshift(self) -> None:
        from asre.migration.versions import _001_initial_schema

        adapter = MagicMock()
        adapter.warehouse_type = "redshift"
        _001_initial_schema.upgrade(adapter)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl
        assert "asre_metadata" in ddl
        assert "VARCHAR" in ddl

    def test_migration_003_output_tables_postgres(self) -> None:
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        adapter.warehouse_type = "postgres"
        _003_output_tables.upgrade(adapter)

        # Should create 5 tables
        assert adapter.execute_ddl.call_count == 5
        for c in adapter.execute_ddl.call_args_list:
            ddl = c[0][0]
            assert "CREATE TABLE" in ddl

    def test_migration_003_output_tables_snowflake(self) -> None:
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        adapter.warehouse_type = "snowflake"
        _003_output_tables.upgrade(adapter)

        assert adapter.execute_ddl.call_count == 5

    def test_migration_003_output_tables_bigquery(self) -> None:
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        adapter.warehouse_type = "bigquery"
        _003_output_tables.upgrade(adapter)

        assert adapter.execute_ddl.call_count == 5
        # BigQuery uses STRING instead of TEXT
        for c in adapter.execute_ddl.call_args_list:
            ddl = c[0][0]
            assert "TEXT" not in ddl or "asre_metadata" in ddl

    def test_migration_003_output_tables_redshift(self) -> None:
        from asre.migration.versions import _003_output_tables

        adapter = MagicMock()
        adapter.warehouse_type = "redshift"
        _003_output_tables.upgrade(adapter)

        assert adapter.execute_ddl.call_count == 5

    def test_migration_004_episode_tables_postgres(self) -> None:
        from asre.migration.versions import _004_episode_tables

        adapter = MagicMock()
        adapter.warehouse_type = "postgres"
        _004_episode_tables.upgrade(adapter)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl
        assert "asre_episodes" in ddl

    def test_migration_004_episode_tables_bigquery(self) -> None:
        from asre.migration.versions import _004_episode_tables

        adapter = MagicMock()
        adapter.warehouse_type = "bigquery"
        _004_episode_tables.upgrade(adapter)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl
        assert "asre_episodes" in ddl
        assert "STRING" in ddl

    def test_migration_004_episode_tables_redshift(self) -> None:
        from asre.migration.versions import _004_episode_tables

        adapter = MagicMock()
        adapter.warehouse_type = "redshift"
        _004_episode_tables.upgrade(adapter)

        ddl = adapter.execute_ddl.call_args[0][0]
        assert "CREATE TABLE" in ddl
        assert "asre_episodes" in ddl
        assert "VARCHAR" in ddl
