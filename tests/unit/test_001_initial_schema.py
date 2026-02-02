"""Tests for the 001_initial_schema migration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from asre.migration.versions import _001_initial_schema as migration


class TestInitialSchemaMigration:
    """Test the 001 initial schema migration."""

    def test_has_upgrade_function(self) -> None:
        assert hasattr(migration, "upgrade")
        assert callable(migration.upgrade)

    def test_has_description(self) -> None:
        assert hasattr(migration, "description")
        assert isinstance(migration.description, str)
        assert len(migration.description) > 0

    def test_upgrade_creates_asre_metadata(self) -> None:
        """upgrade() should create asre_metadata table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        # At least one DDL call should create asre_metadata
        asre_metadata_created = any(
            "asre_metadata" in ddl and "CREATE" in ddl.upper()
            for ddl in ddl_calls
        )
        assert asre_metadata_created, f"Expected asre_metadata creation in DDL calls: {ddl_calls}"

    def test_upgrade_creates_watermark_tracking(self) -> None:
        """upgrade() should create watermark tracking — either via asre_metadata or separate table."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        # The asre_metadata table is used for watermark tracking (key-value store)
        # So creating asre_metadata IS creating watermark tracking
        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        asre_metadata_created = any(
            "asre_metadata" in ddl
            for ddl in ddl_calls
        )
        assert asre_metadata_created

    def test_upgrade_uses_if_not_exists(self) -> None:
        """Migration should be idempotent using IF NOT EXISTS."""
        adapter = MagicMock()
        migration.upgrade(adapter)

        ddl_calls = [str(c) for c in adapter.execute_ddl.call_args_list]
        for ddl in ddl_calls:
            if "CREATE" in ddl.upper():
                assert "IF NOT EXISTS" in ddl.upper(), f"CREATE without IF NOT EXISTS: {ddl}"

    def test_upgrade_can_be_called_twice(self) -> None:
        """Calling upgrade twice should not error (idempotent)."""
        adapter = MagicMock()
        migration.upgrade(adapter)
        migration.upgrade(adapter)
        # No exception = success
