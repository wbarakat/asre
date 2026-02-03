"""Tests for IngestAdapter abstract base class."""

from __future__ import annotations

from abc import ABC
from datetime import datetime, timezone
from typing import Any

import pytest

from asre.ingest.base import IngestAdapter


class TestIngestAdapterIsAbstract:
    """Verify IngestAdapter cannot be instantiated directly."""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            IngestAdapter()  # type: ignore[abstract]

    def test_is_abc_subclass(self) -> None:
        assert issubclass(IngestAdapter, ABC)


class TestIngestAdapterRequiredMethods:
    """Verify all required abstract methods exist."""

    def test_has_connect_method(self) -> None:
        assert hasattr(IngestAdapter, "connect")

    def test_has_disconnect_method(self) -> None:
        assert hasattr(IngestAdapter, "disconnect")

    def test_has_read_source_method(self) -> None:
        assert hasattr(IngestAdapter, "read_source")

    def test_has_get_watermark_method(self) -> None:
        assert hasattr(IngestAdapter, "get_watermark")

    def test_has_set_watermark_method(self) -> None:
        assert hasattr(IngestAdapter, "set_watermark")

    def test_has_execute_ddl_method(self) -> None:
        assert hasattr(IngestAdapter, "execute_ddl")

    def test_has_write_records_method(self) -> None:
        assert hasattr(IngestAdapter, "write_records")


class TestIngestAdapterIncompleteSubclass:
    """Verify incomplete subclasses cannot be instantiated."""

    def test_missing_methods_raises_type_error(self) -> None:
        class PartialAdapter(IngestAdapter):
            def connect(self) -> None:
                pass

        with pytest.raises(TypeError):
            PartialAdapter()  # type: ignore[abstract]


class TestIngestAdapterCompleteSubclass:
    """Verify a complete implementation can be instantiated and called."""

    def _make_adapter(self) -> IngestAdapter:
        class DummyAdapter(IngestAdapter):
            @property
            def warehouse_type(self) -> str:
                return "postgres"

            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

            def read_source(
                self,
                source_name: str,
                query: str,
                params: dict[str, Any] | None = None,
            ) -> list[dict[str, Any]]:
                return [{"id": 1}]

            def get_watermark(self, source_name: str) -> datetime | None:
                return None

            def set_watermark(self, source_name: str, watermark: datetime) -> None:
                pass

            def execute_ddl(self, ddl: str) -> None:
                pass

            def write_records(
                self,
                table_name: str,
                records: list[dict[str, Any]],
            ) -> int:
                return len(records)

        return DummyAdapter()

    def test_complete_subclass_instantiates(self) -> None:
        adapter = self._make_adapter()
        assert isinstance(adapter, IngestAdapter)

    def test_connect_callable(self) -> None:
        adapter = self._make_adapter()
        adapter.connect()  # should not raise

    def test_disconnect_callable(self) -> None:
        adapter = self._make_adapter()
        adapter.disconnect()  # should not raise

    def test_read_source_returns_list_of_dicts(self) -> None:
        adapter = self._make_adapter()
        result = adapter.read_source("test_source", "SELECT 1")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == {"id": 1}

    def test_get_watermark_returns_none_or_datetime(self) -> None:
        adapter = self._make_adapter()
        result = adapter.get_watermark("test_source")
        assert result is None

    def test_set_watermark_callable(self) -> None:
        adapter = self._make_adapter()
        now = datetime.now(timezone.utc)
        adapter.set_watermark("test_source", now)  # should not raise

    def test_execute_ddl_callable(self) -> None:
        adapter = self._make_adapter()
        adapter.execute_ddl("CREATE TABLE test (id INT)")  # should not raise

    def test_write_records_returns_count(self) -> None:
        adapter = self._make_adapter()
        records = [{"a": 1}, {"a": 2}]
        count = adapter.write_records("test_table", records)
        assert count == 2
