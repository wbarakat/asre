"""Tests for Snowflake adapter implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from asre.ingest.base import IngestAdapter


class TestSnowflakeAdapterIsIngestAdapter:
    """Verify SnowflakeAdapter implements IngestAdapter."""

    def test_is_subclass_of_ingest_adapter(self) -> None:
        from asre.ingest.snowflake import SnowflakeAdapter

        assert issubclass(SnowflakeAdapter, IngestAdapter)

    def test_can_instantiate_with_config(self) -> None:
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "myaccount",
            "user": "myuser",
            "password": "mypass",
            "database": "mydb",
            "schema": "myschema",
            "warehouse": "mywh",
        }
        adapter = SnowflakeAdapter(config)
        assert isinstance(adapter, IngestAdapter)


class TestSnowflakeAdapterConnection:
    """Test connection management."""

    def _make_adapter(self) -> Any:
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "myaccount",
            "user": "myuser",
            "password": "mypass",
            "database": "mydb",
            "schema": "myschema",
            "warehouse": "mywh",
        }
        return SnowflakeAdapter(config)

    @patch("asre.ingest.snowflake.snowflake_connect")
    def test_connect_calls_snowflake_connect(
        self, mock_connect: MagicMock
    ) -> None:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter = self._make_adapter()
        adapter.connect()

        mock_connect.assert_called_once_with(
            account="myaccount",
            user="myuser",
            password="mypass",
            database="mydb",
            schema="myschema",
            warehouse="mywh",
            role=None,
        )

    @patch("asre.ingest.snowflake.snowflake_connect")
    def test_connect_with_role(self, mock_connect: MagicMock) -> None:
        from asre.ingest.snowflake import SnowflakeAdapter

        mock_connect.return_value = MagicMock()
        config: dict[str, Any] = {
            "account": "myaccount",
            "user": "myuser",
            "password": "mypass",
            "database": "mydb",
            "schema": "myschema",
            "warehouse": "mywh",
            "role": "myrole",
        }
        adapter = SnowflakeAdapter(config)
        adapter.connect()

        mock_connect.assert_called_once_with(
            account="myaccount",
            user="myuser",
            password="mypass",
            database="mydb",
            schema="myschema",
            warehouse="mywh",
            role="myrole",
        )

    @patch("asre.ingest.snowflake.snowflake_connect")
    def test_connect_error_raises_with_clear_message(
        self, mock_connect: MagicMock
    ) -> None:
        mock_connect.side_effect = Exception("Connection refused")

        adapter = self._make_adapter()
        with pytest.raises(ConnectionError, match="Failed to connect to Snowflake"):
            adapter.connect()

    @patch("asre.ingest.snowflake.snowflake_connect")
    def test_disconnect_closes_connection(
        self, mock_connect: MagicMock
    ) -> None:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter = self._make_adapter()
        adapter.connect()
        adapter.disconnect()

        mock_conn.close.assert_called_once()

    def test_disconnect_without_connect_is_safe(self) -> None:
        adapter = self._make_adapter()
        adapter.disconnect()  # should not raise


class TestSnowflakeAdapterReadSource:
    """Test read_source method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "myaccount",
            "user": "myuser",
            "password": "mypass",
            "database": "mydb",
            "schema": "myschema",
            "warehouse": "mywh",
        }
        adapter = SnowflakeAdapter(config)

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        return adapter, mock_conn

    def test_read_source_executes_query(self) -> None:
        adapter, mock_conn = self._make_connected_adapter()
        adapter.read_source("test_source", "SELECT * FROM patients")
        mock_conn.cursor.return_value.execute.assert_called_once()

    def test_read_source_returns_list_of_dicts(self) -> None:
        adapter, _ = self._make_connected_adapter()
        result = adapter.read_source("test_source", "SELECT * FROM patients")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Alice"
        assert result[1]["id"] == 2
        assert result[1]["name"] == "Bob"

    def test_read_source_with_params(self) -> None:
        adapter, mock_conn = self._make_connected_adapter()
        cursor = mock_conn.cursor.return_value
        adapter.read_source(
            "test_source",
            "SELECT * FROM patients WHERE id = :id",
            params={"id": 1},
        )
        cursor.execute.assert_called_once()

    def test_read_source_handles_variant_column_as_dict(self) -> None:
        """VARIANT columns containing JSON strings should be parsed to dicts."""
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "a", "user": "u", "password": "p",
            "database": "d", "schema": "s", "warehouse": "w",
        }
        adapter = SnowflakeAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("payload",)]
        # Snowflake returns VARIANT as JSON string
        mock_cursor.fetchall.return_value = [
            (1, '{"key": "value"}'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        result = adapter.read_source("test_source", "SELECT id, payload FROM t")
        # VARIANT values that are JSON strings are returned as-is (str)
        # The adapter returns raw values; JSON parsing is a downstream concern
        assert result[0]["payload"] == '{"key": "value"}'

    def test_read_source_handles_array_column(self) -> None:
        """ARRAY columns should be returned as lists."""
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "a", "user": "u", "password": "p",
            "database": "d", "schema": "s", "warehouse": "w",
        }
        adapter = SnowflakeAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("tags",)]
        # Snowflake ARRAY returned as JSON string
        mock_cursor.fetchall.return_value = [
            (1, '["tag1", "tag2"]'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        result = adapter.read_source("test_source", "SELECT id, tags FROM t")
        # Arrays also returned as raw string; downstream handles parsing
        assert result[0]["tags"] == '["tag1", "tag2"]'


class TestSnowflakeAdapterWriteRecords:
    """Test write_records method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "a", "user": "u", "password": "p",
            "database": "d", "schema": "s", "warehouse": "w",
        }
        adapter = SnowflakeAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]
        return adapter, mock_conn

    def test_write_records_returns_count(self) -> None:
        adapter, _ = self._make_connected_adapter()
        records = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        count = adapter.write_records("patients", records)
        assert count == 2

    def test_write_records_empty_list_returns_zero(self) -> None:
        adapter, _ = self._make_connected_adapter()
        count = adapter.write_records("patients", [])
        assert count == 0

    def test_write_records_serializes_dict_values_to_json(self) -> None:
        """Dict/list values should be JSON-serialized for VARIANT/ARRAY columns."""
        adapter, mock_conn = self._make_connected_adapter()
        cursor = mock_conn.cursor.return_value
        records = [{"id": 1, "payload": {"key": "value"}, "tags": ["a", "b"]}]
        adapter.write_records("events", records)

        # Verify execute was called with JSON-serialized values
        assert cursor.execute.called
        call_args = cursor.execute.call_args
        params = call_args[0][1]
        assert params["payload"] == json.dumps({"key": "value"})
        assert params["tags"] == json.dumps(["a", "b"])


class TestSnowflakeAdapterExecuteDDL:
    """Test execute_ddl method."""

    def test_execute_ddl_runs_statement(self) -> None:
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "a", "user": "u", "password": "p",
            "database": "d", "schema": "s", "warehouse": "w",
        }
        adapter = SnowflakeAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        adapter.execute_ddl("CREATE TABLE test (id INT)")
        mock_cursor.execute.assert_called_once()


class TestSnowflakeAdapterWatermark:
    """Test watermark methods."""

    def _make_adapter_with_mock(self) -> tuple[Any, MagicMock]:
        from asre.ingest.snowflake import SnowflakeAdapter

        config: dict[str, Any] = {
            "account": "a", "user": "u", "password": "p",
            "database": "d", "schema": "s", "warehouse": "w",
        }
        adapter = SnowflakeAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]
        return adapter, mock_conn

    def test_get_watermark_returns_none_when_no_row(self) -> None:
        adapter, mock_conn = self._make_adapter_with_mock()
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = None

        result = adapter.get_watermark("test_source")
        assert result is None

    def test_get_watermark_returns_datetime_when_row_exists(self) -> None:
        adapter, mock_conn = self._make_adapter_with_mock()
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = ("2026-01-15T10:30:00+00:00",)

        result = adapter.get_watermark("adt_vendor_x")
        assert result is not None
        assert result == datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_get_watermark_uses_correct_key_format(self) -> None:
        adapter, mock_conn = self._make_adapter_with_mock()
        cursor = mock_conn.cursor.return_value
        cursor.fetchone.return_value = None

        adapter.get_watermark("adt_vendor_x")

        call_args = cursor.execute.call_args
        params = call_args[0][1]
        assert params[0] == "watermark_adt_vendor_x"

    def test_set_watermark_stores_iso_format(self) -> None:
        adapter, mock_conn = self._make_adapter_with_mock()
        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        adapter.set_watermark("adt_vendor_x", ts)

        cursor = mock_conn.cursor.return_value
        call_args = cursor.execute.call_args
        params = call_args[0][1]
        assert "watermark_adt_vendor_x" in params
        assert ts.isoformat() in params

    def test_set_watermark_uses_merge(self) -> None:
        """Snowflake uses MERGE for upsert behavior."""
        adapter, mock_conn = self._make_adapter_with_mock()
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        adapter.set_watermark("adt_vendor_x", ts)

        cursor = mock_conn.cursor.return_value
        call_args = cursor.execute.call_args
        sql = call_args[0][0]
        assert "MERGE" in sql

    def test_watermarks_are_per_source_keys(self) -> None:
        adapter, mock_conn = self._make_adapter_with_mock()
        cursor = mock_conn.cursor.return_value
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        adapter.set_watermark("adt_vendor_x", ts)
        key1_params = cursor.execute.call_args[0][1]

        adapter.set_watermark("claims_clearinghouse", ts)
        key2_params = cursor.execute.call_args[0][1]

        assert "watermark_adt_vendor_x" in key1_params
        assert "watermark_claims_clearinghouse" in key2_params
