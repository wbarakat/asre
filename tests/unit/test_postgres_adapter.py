"""Tests for PostgreSQL adapter implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from asre.ingest.base import IngestAdapter


class TestPostgresAdapterIsIngestAdapter:
    """Verify PostgresAdapter implements IngestAdapter."""

    def test_is_subclass_of_ingest_adapter(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        assert issubclass(PostgresAdapter, IngestAdapter)

    def test_can_instantiate_with_config(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)
        assert isinstance(adapter, IngestAdapter)


class TestPostgresAdapterConnection:
    """Test connection management."""

    def _make_adapter(self) -> Any:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        return PostgresAdapter(config)

    @patch("asre.ingest.postgres.create_engine")
    def test_connect_creates_engine_and_connection(
        self, mock_create_engine: MagicMock
    ) -> None:
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_engine.connect.return_value = mock_connection
        mock_create_engine.return_value = mock_engine

        adapter = self._make_adapter()
        adapter.connect()

        mock_create_engine.assert_called_once()
        call_args = mock_create_engine.call_args
        url = str(call_args[0][0])
        assert "postgresql" in url
        assert "testuser" in url
        assert "testdb" in url

    @patch("asre.ingest.postgres.create_engine")
    def test_connect_error_raises_with_clear_message(
        self, mock_create_engine: MagicMock
    ) -> None:
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection refused")
        mock_create_engine.return_value = mock_engine

        adapter = self._make_adapter()
        with pytest.raises(ConnectionError, match="Failed to connect"):
            adapter.connect()

    @patch("asre.ingest.postgres.create_engine")
    def test_disconnect_closes_connection(
        self, mock_create_engine: MagicMock
    ) -> None:
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_engine.connect.return_value = mock_connection
        mock_create_engine.return_value = mock_engine

        adapter = self._make_adapter()
        adapter.connect()
        adapter.disconnect()

        mock_connection.close.assert_called_once()

    @patch("asre.ingest.postgres.create_engine")
    def test_disconnect_also_disposes_engine(
        self, mock_create_engine: MagicMock
    ) -> None:
        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_engine.connect.return_value = mock_connection
        mock_create_engine.return_value = mock_engine

        adapter = self._make_adapter()
        adapter.connect()
        adapter.disconnect()

        mock_engine.dispose.assert_called_once()

    def test_disconnect_without_connect_is_safe(self) -> None:
        adapter = self._make_adapter()
        adapter.disconnect()  # should not raise


class TestPostgresAdapterReadSource:
    """Test read_source method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)

        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        mock_connection.execute.return_value = mock_result
        adapter._connection = mock_connection  # type: ignore[attr-defined]

        return adapter, mock_connection

    def test_read_source_executes_query(self) -> None:
        adapter, mock_conn = self._make_connected_adapter()
        result = adapter.read_source("test_source", "SELECT * FROM patients")
        assert mock_conn.execute.called

    def test_read_source_returns_list_of_dicts(self) -> None:
        adapter, _ = self._make_connected_adapter()
        result = adapter.read_source("test_source", "SELECT * FROM patients")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["name"] == "Bob"

    def test_read_source_with_params(self) -> None:
        adapter, mock_conn = self._make_connected_adapter()
        adapter.read_source(
            "test_source",
            "SELECT * FROM patients WHERE id = :id",
            params={"id": 1},
        )
        assert mock_conn.execute.called


class TestPostgresAdapterExecuteDDL:
    """Test execute_ddl method."""

    def test_execute_ddl_runs_statement(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)
        mock_connection = MagicMock()
        adapter._connection = mock_connection  # type: ignore[attr-defined]

        adapter.execute_ddl("CREATE TABLE test (id INT)")
        assert mock_connection.execute.called
        mock_connection.commit.assert_called_once()


class TestPostgresAdapterWriteRecords:
    """Test write_records method."""

    def test_write_records_returns_count(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)
        mock_connection = MagicMock()
        adapter._connection = mock_connection  # type: ignore[attr-defined]

        records = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        count = adapter.write_records("patients", records)
        assert count == 2

    def test_write_records_empty_list_returns_zero(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)
        mock_connection = MagicMock()
        adapter._connection = mock_connection  # type: ignore[attr-defined]

        count = adapter.write_records("patients", [])
        assert count == 0


class TestPostgresAdapterWatermark:
    """Test watermark methods (basic stubs since full watermark is US-024)."""

    def test_get_watermark_returns_none_by_default(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_connection.execute.return_value = mock_result
        adapter._connection = mock_connection  # type: ignore[attr-defined]

        result = adapter.get_watermark("test_source")
        assert result is None

    def test_set_watermark_callable(self) -> None:
        from asre.ingest.postgres import PostgresAdapter

        config: dict[str, Any] = {
            "host": "localhost",
            "port": "5432",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
            "schema": "public",
        }
        adapter = PostgresAdapter(config)
        mock_connection = MagicMock()
        adapter._connection = mock_connection  # type: ignore[attr-defined]

        now = datetime.now(timezone.utc)
        adapter.set_watermark("test_source", now)
        assert mock_connection.execute.called


class TestPostgresAdapterConnectionUrl:
    """Test connection URL construction."""

    @patch("asre.ingest.postgres.create_engine")
    def test_uses_schema_in_search_path(
        self, mock_create_engine: MagicMock
    ) -> None:
        from asre.ingest.postgres import PostgresAdapter

        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_engine.connect.return_value = mock_connection
        mock_create_engine.return_value = mock_engine

        config: dict[str, Any] = {
            "host": "myhost",
            "port": "5433",
            "database": "mydb",
            "user": "myuser",
            "password": "mypass",
            "schema": "asre_schema",
        }
        adapter = PostgresAdapter(config)
        adapter.connect()

        call_args = mock_create_engine.call_args
        url = str(call_args[0][0])
        assert "myhost" in url
        assert "5433" in url
        assert "mydb" in url
        assert "myuser" in url

    @patch("asre.ingest.postgres.create_engine")
    def test_default_port_when_not_specified(
        self, mock_create_engine: MagicMock
    ) -> None:
        from asre.ingest.postgres import PostgresAdapter

        mock_engine = MagicMock()
        mock_connection = MagicMock()
        mock_engine.connect.return_value = mock_connection
        mock_create_engine.return_value = mock_engine

        config: dict[str, Any] = {
            "host": "localhost",
            "database": "testdb",
            "user": "testuser",
            "password": "testpass",
        }
        adapter = PostgresAdapter(config)
        adapter.connect()

        call_args = mock_create_engine.call_args
        url = str(call_args[0][0])
        assert "5432" in url
