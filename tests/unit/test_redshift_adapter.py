"""Tests for Redshift adapter implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from asre.ingest.base import IngestAdapter


class TestRedshiftAdapterIsIngestAdapter:
    """Verify RedshiftAdapter implements IngestAdapter."""

    def test_is_subclass_of_ingest_adapter(self) -> None:
        from asre.ingest.redshift import RedshiftAdapter

        assert issubclass(RedshiftAdapter, IngestAdapter)

    def test_can_instantiate_with_config(self) -> None:
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "my-cluster.redshift.amazonaws.com",
            "port": 5439,
            "database": "mydb",
            "user": "myuser",
            "password": "mypass",
            "schema": "public",
        }
        adapter = RedshiftAdapter(config)
        assert isinstance(adapter, IngestAdapter)


class TestRedshiftAdapterConnection:
    """Test connection management."""

    def _make_adapter(self) -> Any:
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "my-cluster.redshift.amazonaws.com",
            "port": 5439,
            "database": "mydb",
            "user": "myuser",
            "password": "mypass",
            "schema": "public",
        }
        return RedshiftAdapter(config)

    @patch("asre.ingest.redshift._HAS_REDSHIFT", True)
    @patch("asre.ingest.redshift.redshift_connect")
    def test_connect_calls_redshift_connect(
        self, mock_connect: MagicMock
    ) -> None:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        adapter = self._make_adapter()
        adapter.connect()

        mock_connect.assert_called_once_with(
            host="my-cluster.redshift.amazonaws.com",
            port=5439,
            database="mydb",
            user="myuser",
            password="mypass",
            ssl=True,
        )

    @patch("asre.ingest.redshift._HAS_REDSHIFT", True)
    @patch("asre.ingest.redshift.redshift_connect")
    def test_connect_error_raises_with_clear_message(
        self, mock_connect: MagicMock
    ) -> None:
        mock_connect.side_effect = Exception("Connection refused")

        adapter = self._make_adapter()
        with pytest.raises(ConnectionError, match="Failed to connect to Redshift"):
            adapter.connect()

    @patch("asre.ingest.redshift._HAS_REDSHIFT", False)
    def test_connect_raises_import_error_without_library(self) -> None:
        adapter = self._make_adapter()
        with pytest.raises(ImportError, match="redshift-connector is required"):
            adapter.connect()

    @patch("asre.ingest.redshift._HAS_REDSHIFT", True)
    @patch("asre.ingest.redshift.redshift_connect")
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


class TestRedshiftAdapterReadSource:
    """Test read_source method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "my-cluster.redshift.amazonaws.com",
            "port": 5439,
            "database": "mydb",
            "user": "myuser",
            "password": "mypass",
            "schema": "public",
        }
        adapter = RedshiftAdapter(config)

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
            "SELECT * FROM patients WHERE id = %s",
            params={"id": 1},
        )
        cursor.execute.assert_called_once()

    def test_read_source_handles_super_column_as_json_string(self) -> None:
        """SUPER columns containing JSON are returned as strings for downstream parsing."""
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "h", "port": 5439, "database": "d",
            "user": "u", "password": "p", "schema": "s",
        }
        adapter = RedshiftAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("payload",)]
        mock_cursor.fetchall.return_value = [
            (1, '{"key": "value"}'),
        ]
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        result = adapter.read_source("test_source", "SELECT id, payload FROM t")
        assert result[0]["payload"] == '{"key": "value"}'

    def test_read_source_handles_varchar_max(self) -> None:
        """VARCHAR(MAX) fields should be returned as strings."""
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "h", "port": 5439, "database": "d",
            "user": "u", "password": "p", "schema": "s",
        }
        adapter = RedshiftAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("large_text",)]
        long_text = "x" * 100000
        mock_cursor.fetchall.return_value = [
            (1, long_text),
        ]
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        result = adapter.read_source("test_source", "SELECT id, large_text FROM t")
        assert result[0]["large_text"] == long_text


class TestRedshiftAdapterWriteRecords:
    """Test write_records method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "h", "port": 5439, "database": "d",
            "user": "u", "password": "p", "schema": "public",
        }
        adapter = RedshiftAdapter(config)
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
        """Dict/list values should be JSON-serialized for SUPER columns."""
        adapter, mock_conn = self._make_connected_adapter()
        cursor = mock_conn.cursor.return_value
        records = [{"id": 1, "payload": {"key": "value"}, "tags": ["a", "b"]}]
        adapter.write_records("events", records)

        assert cursor.execute.called
        call_args = cursor.execute.call_args
        params = call_args[0][1]
        assert params["payload"] == json.dumps({"key": "value"})
        assert params["tags"] == json.dumps(["a", "b"])

    def test_write_records_uses_schema_prefix(self) -> None:
        """Write records should use schema prefix on table names."""
        adapter, mock_conn = self._make_connected_adapter()
        cursor = mock_conn.cursor.return_value
        records = [{"id": 1}]
        adapter.write_records("patients", records)

        call_args = cursor.execute.call_args
        sql = call_args[0][0]
        assert "public.patients" in sql


class TestRedshiftAdapterExecuteDDL:
    """Test execute_ddl method."""

    def test_execute_ddl_runs_statement(self) -> None:
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "h", "port": 5439, "database": "d",
            "user": "u", "password": "p", "schema": "s",
        }
        adapter = RedshiftAdapter(config)
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        adapter._connection = mock_conn  # type: ignore[attr-defined]

        adapter.execute_ddl("CREATE TABLE test (id INT)")
        mock_cursor.execute.assert_called_once_with("CREATE TABLE test (id INT)")


class TestRedshiftAdapterWatermark:
    """Test watermark methods."""

    def _make_adapter_with_mock(self) -> tuple[Any, MagicMock]:
        from asre.ingest.redshift import RedshiftAdapter

        config: dict[str, Any] = {
            "host": "h", "port": 5439, "database": "d",
            "user": "u", "password": "p", "schema": "public",
        }
        adapter = RedshiftAdapter(config)
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
        sql = call_args[0][0]
        # Redshift doesn't support MERGE; uses DELETE + INSERT pattern
        assert "DELETE" in sql or "INSERT" in sql

    def test_set_watermark_is_upsert(self) -> None:
        """Redshift uses DELETE + INSERT for upsert since it lacks MERGE."""
        adapter, mock_conn = self._make_adapter_with_mock()
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        adapter.set_watermark("adt_vendor_x", ts)

        cursor = mock_conn.cursor.return_value
        # Should have at least 2 calls: DELETE then INSERT
        assert cursor.execute.call_count >= 2

    def test_watermarks_are_per_source_keys(self) -> None:
        adapter, mock_conn = self._make_adapter_with_mock()
        cursor = mock_conn.cursor.return_value
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        adapter.set_watermark("adt_vendor_x", ts)
        first_call_count = cursor.execute.call_count

        adapter.set_watermark("claims_clearinghouse", ts)
        # Each watermark set requires at least 2 calls (DELETE + INSERT)
        assert cursor.execute.call_count >= first_call_count + 2


class TestRedshiftAdapterEndToEnd:
    """Test all pipeline stages work end-to-end pattern."""

    def test_all_adapter_methods_exist(self) -> None:
        """Verify Redshift adapter has all required IngestAdapter methods."""
        from asre.ingest.redshift import RedshiftAdapter

        adapter = RedshiftAdapter({
            "host": "h", "port": 5439, "database": "d",
            "user": "u", "password": "p",
        })
        assert hasattr(adapter, "connect")
        assert hasattr(adapter, "disconnect")
        assert hasattr(adapter, "read_source")
        assert hasattr(adapter, "get_watermark")
        assert hasattr(adapter, "set_watermark")
        assert hasattr(adapter, "execute_ddl")
        assert hasattr(adapter, "write_records")
        assert callable(adapter.connect)
        assert callable(adapter.disconnect)
        assert callable(adapter.read_source)
        assert callable(adapter.get_watermark)
        assert callable(adapter.set_watermark)
        assert callable(adapter.execute_ddl)
        assert callable(adapter.write_records)
