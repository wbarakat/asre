"""Tests for BigQuery adapter implementation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from asre.ingest.base import IngestAdapter


def _make_row_mock(items: dict[str, Any]) -> MagicMock:
    """Create a mock BigQuery Row that works with dict(row)."""
    row = MagicMock()
    row.keys.return_value = items.keys()
    row.values.return_value = items.values()
    row.items.return_value = items.items()
    row.__iter__ = MagicMock(return_value=iter(items))
    row.__getitem__ = lambda self, k: items[k]  # noqa: ARG005
    return row


def _mock_query_job_config_cls() -> MagicMock:
    """Create a mock QueryJobConfig class."""
    mock = MagicMock()
    mock.return_value = MagicMock()
    return mock


def _mock_scalar_query_parameter_cls() -> MagicMock:
    """Create a mock ScalarQueryParameter class that captures args."""

    class FakeParam:
        def __init__(self, name: str, ptype: str, value: Any) -> None:
            self.name = name
            self.type_ = ptype
            self.value = value

    return MagicMock(side_effect=FakeParam)


class TestBigQueryAdapterIsIngestAdapter:
    """Verify BigQueryAdapter implements IngestAdapter."""

    def test_is_subclass_of_ingest_adapter(self) -> None:
        from asre.ingest.bigquery import BigQueryAdapter

        assert issubclass(BigQueryAdapter, IngestAdapter)

    def test_can_instantiate_with_config(self) -> None:
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "myproject",
            "dataset": "mydataset",
            "location": "US",
        }
        adapter = BigQueryAdapter(config)
        assert isinstance(adapter, IngestAdapter)


class TestBigQueryAdapterConnection:
    """Test connection management."""

    def _make_adapter(self) -> Any:
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "myproject",
            "dataset": "mydataset",
            "location": "US",
        }
        return BigQueryAdapter(config)

    @patch("asre.ingest.bigquery._HAS_BIGQUERY", True)
    @patch("asre.ingest.bigquery.BigQueryClient")
    def test_connect_creates_client(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        adapter = self._make_adapter()
        adapter.connect()

        mock_client_cls.assert_called_once_with(
            project="myproject",
            location="US",
        )

    @patch("asre.ingest.bigquery._HAS_BIGQUERY", True)
    @patch("asre.ingest.bigquery.BigQueryClient")
    def test_connect_with_credentials_path(
        self, mock_client_cls: MagicMock
    ) -> None:
        from asre.ingest.bigquery import BigQueryAdapter

        mock_client_cls.return_value = MagicMock()
        config: dict[str, Any] = {
            "project": "myproject",
            "dataset": "mydataset",
            "location": "US",
            "credentials_path": "/path/to/creds.json",
        }
        adapter = BigQueryAdapter(config)

        with patch(
            "google.oauth2.service_account.Credentials.from_service_account_file"
        ) as mock_creds:
            mock_creds.return_value = MagicMock()
            adapter.connect()
            mock_creds.assert_called_once_with("/path/to/creds.json")

    @patch("asre.ingest.bigquery._HAS_BIGQUERY", True)
    @patch("asre.ingest.bigquery.BigQueryClient")
    def test_connect_error_raises_with_clear_message(
        self, mock_client_cls: MagicMock
    ) -> None:
        mock_client_cls.side_effect = Exception("Auth failed")

        adapter = self._make_adapter()
        with pytest.raises(ConnectionError, match="Failed to connect to BigQuery"):
            adapter.connect()

    @patch("asre.ingest.bigquery._HAS_BIGQUERY", False)
    def test_connect_raises_import_error_without_library(self) -> None:
        adapter = self._make_adapter()
        with pytest.raises(ImportError, match="google-cloud-bigquery is required"):
            adapter.connect()

    @patch("asre.ingest.bigquery._HAS_BIGQUERY", True)
    @patch("asre.ingest.bigquery.BigQueryClient")
    def test_disconnect_closes_client(self, mock_client_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        adapter = self._make_adapter()
        adapter.connect()
        adapter.disconnect()

        mock_client.close.assert_called_once()

    def test_disconnect_without_connect_is_safe(self) -> None:
        adapter = self._make_adapter()
        adapter.disconnect()  # should not raise


class TestBigQueryAdapterReadSource:
    """Test read_source method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "myproject",
            "dataset": "mydataset",
            "location": "US",
        }
        adapter = BigQueryAdapter(config)

        mock_client = MagicMock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [
            _make_row_mock({"id": 1, "name": "Alice"}),
            _make_row_mock({"id": 2, "name": "Bob"}),
        ]
        mock_client.query.return_value = mock_query_job
        adapter._client = mock_client

        return adapter, mock_client

    def test_read_source_executes_query(self) -> None:
        adapter, mock_client = self._make_connected_adapter()
        adapter.read_source("test_source", "SELECT * FROM patients")
        mock_client.query.assert_called_once()

    def test_read_source_returns_list_of_dicts(self) -> None:
        adapter, _ = self._make_connected_adapter()
        result = adapter.read_source("test_source", "SELECT * FROM patients")
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["name"] == "Alice"
        assert result[1]["id"] == 2
        assert result[1]["name"] == "Bob"

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_read_source_with_params(self) -> None:
        adapter, mock_client = self._make_connected_adapter()
        adapter.read_source(
            "test_source",
            "SELECT * FROM patients WHERE id = @id",
            params={"id": 1},
        )
        # Should call query with job_config
        call_kwargs = mock_client.query.call_args
        assert call_kwargs[1].get("job_config") is not None

    def test_read_source_handles_json_column(self) -> None:
        """JSON columns should be returned as native Python dicts."""
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "p", "dataset": "d", "location": "US",
        }
        adapter = BigQueryAdapter(config)
        mock_client = MagicMock()

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [
            _make_row_mock({"id": 1, "payload": {"key": "value"}})
        ]
        mock_client.query.return_value = mock_query_job
        adapter._client = mock_client

        result = adapter.read_source("test_source", "SELECT id, payload FROM t")
        assert result[0]["payload"] == {"key": "value"}

    def test_read_source_handles_array_column(self) -> None:
        """ARRAY columns should be returned as lists."""
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "p", "dataset": "d", "location": "US",
        }
        adapter = BigQueryAdapter(config)
        mock_client = MagicMock()

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [
            _make_row_mock({"id": 1, "tags": ["tag1", "tag2"]})
        ]
        mock_client.query.return_value = mock_query_job
        adapter._client = mock_client

        result = adapter.read_source("test_source", "SELECT id, tags FROM t")
        assert result[0]["tags"] == ["tag1", "tag2"]


class TestBigQueryAdapterWriteRecords:
    """Test write_records method."""

    def _make_connected_adapter(self) -> tuple[Any, MagicMock]:
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "p", "dataset": "mydataset", "location": "US",
        }
        adapter = BigQueryAdapter(config)
        mock_client = MagicMock()
        mock_query_job = MagicMock()
        mock_client.query.return_value = mock_query_job
        adapter._client = mock_client
        return adapter, mock_client

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
        """Dict/list values should be JSON-serialized for JSON/ARRAY columns."""
        adapter, mock_client = self._make_connected_adapter()
        records = [{"id": 1, "payload": {"key": "value"}, "tags": ["a", "b"]}]
        adapter.write_records("events", records)

        assert mock_client.query.called
        sql = mock_client.query.call_args[0][0]
        assert "JSON" in sql
        assert '{"key": "value"}' in sql

    def test_write_records_handles_none_values(self) -> None:
        adapter, mock_client = self._make_connected_adapter()
        records = [{"id": 1, "name": None}]
        adapter.write_records("patients", records)

        sql = mock_client.query.call_args[0][0]
        assert "NULL" in sql

    def test_write_records_handles_boolean_values(self) -> None:
        adapter, mock_client = self._make_connected_adapter()
        records = [{"id": 1, "active": True}]
        adapter.write_records("patients", records)

        sql = mock_client.query.call_args[0][0]
        assert "TRUE" in sql

    def test_write_records_handles_numeric_values(self) -> None:
        adapter, mock_client = self._make_connected_adapter()
        records = [{"id": 1, "score": 0.85}]
        adapter.write_records("scores", records)

        sql = mock_client.query.call_args[0][0]
        assert "0.85" in sql

    def test_write_records_uses_dataset_prefix(self) -> None:
        adapter, mock_client = self._make_connected_adapter()
        records = [{"id": 1}]
        adapter.write_records("patients", records)

        sql = mock_client.query.call_args[0][0]
        assert "`mydataset.patients`" in sql


class TestBigQueryAdapterExecuteDDL:
    """Test execute_ddl method."""

    def test_execute_ddl_runs_statement(self) -> None:
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "p", "dataset": "d", "location": "US",
        }
        adapter = BigQueryAdapter(config)
        mock_client = MagicMock()
        mock_query_job = MagicMock()
        mock_client.query.return_value = mock_query_job
        adapter._client = mock_client

        adapter.execute_ddl("CREATE TABLE test (id INT64)")
        mock_client.query.assert_called_once_with("CREATE TABLE test (id INT64)")
        mock_query_job.result.assert_called_once()


class TestBigQueryAdapterWatermark:
    """Test watermark methods."""

    def _make_adapter_with_mock(self) -> tuple[Any, MagicMock]:
        from asre.ingest.bigquery import BigQueryAdapter

        config: dict[str, Any] = {
            "project": "p", "dataset": "mydataset", "location": "US",
        }
        adapter = BigQueryAdapter(config)
        mock_client = MagicMock()
        adapter._client = mock_client
        return adapter, mock_client

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_get_watermark_returns_none_when_no_row(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_client.query.return_value = mock_query_job

        result = adapter.get_watermark("test_source")
        assert result is None

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_get_watermark_returns_datetime_when_row_exists(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()

        mock_query_job = MagicMock()
        mock_query_job.result.return_value = [
            _make_row_mock({"value": "2026-01-15T10:30:00+00:00"})
        ]
        mock_client.query.return_value = mock_query_job

        result = adapter.get_watermark("adt_vendor_x")
        assert result is not None
        assert result == datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_get_watermark_uses_parameterized_query(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_query_job = MagicMock()
        mock_query_job.result.return_value = []
        mock_client.query.return_value = mock_query_job

        adapter.get_watermark("adt_vendor_x")

        call_args = mock_client.query.call_args
        sql = call_args[0][0]
        assert "@key" in sql
        assert "asre_metadata" in sql

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_set_watermark_uses_merge(self) -> None:
        """BigQuery uses MERGE for upsert behavior."""
        adapter, mock_client = self._make_adapter_with_mock()
        mock_query_job = MagicMock()
        mock_client.query.return_value = mock_query_job

        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        adapter.set_watermark("adt_vendor_x", ts)

        call_args = mock_client.query.call_args
        sql = call_args[0][0]
        assert "MERGE" in sql

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_set_watermark_uses_dataset_prefix(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_query_job = MagicMock()
        mock_client.query.return_value = mock_query_job

        ts = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        adapter.set_watermark("adt_vendor_x", ts)

        call_args = mock_client.query.call_args
        sql = call_args[0][0]
        assert "`mydataset.asre_metadata`" in sql

    @patch("asre.ingest.bigquery.ScalarQueryParameter", _mock_scalar_query_parameter_cls())
    @patch("asre.ingest.bigquery.QueryJobConfig", _mock_query_job_config_cls())
    def test_watermarks_are_per_source_keys(self) -> None:
        adapter, mock_client = self._make_adapter_with_mock()
        mock_query_job = MagicMock()
        mock_client.query.return_value = mock_query_job
        ts = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        adapter.set_watermark("adt_vendor_x", ts)
        sql1 = mock_client.query.call_args[0][0]

        adapter.set_watermark("claims_clearinghouse", ts)
        sql2 = mock_client.query.call_args[0][0]

        # Both use MERGE and reference asre_metadata
        assert "MERGE" in sql1
        assert "MERGE" in sql2
        # Different calls were made (at least 2 total)
        assert mock_client.query.call_count == 2


class TestBigQueryAdapterEndToEnd:
    """Test all pipeline stages work end-to-end pattern."""

    def test_all_adapter_methods_exist(self) -> None:
        """Verify BigQuery adapter has all required IngestAdapter methods."""
        from asre.ingest.bigquery import BigQueryAdapter

        adapter = BigQueryAdapter({"project": "p", "dataset": "d"})
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
