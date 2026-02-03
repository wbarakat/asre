"""Redshift adapter implementing IngestAdapter using redshift-connector."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

try:
    from redshift_connector import connect as redshift_connect

    _HAS_REDSHIFT = True
except ImportError:
    redshift_connect = None
    _HAS_REDSHIFT = False

from asre.ingest.base import IngestAdapter


class RedshiftAdapter(IngestAdapter):
    """Redshift implementation of IngestAdapter.

    Uses redshift-connector for database operations.
    Handles SUPER type for JSON columns and VARCHAR(MAX) for large text fields.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._connection: Any = None
        self._schema: str = config.get("schema", "public")

    def connect(self) -> None:
        """Establish connection to Redshift using config credentials."""
        if not _HAS_REDSHIFT:
            raise ImportError(
                "redshift-connector is required for the Redshift adapter. "
                "Install it with: pip install redshift-connector"
            )

        host = self._config.get("host", "")
        port = self._config.get("port", 5439)
        database = self._config.get("database", "")
        user = self._config.get("user", "")
        password = self._config.get("password", "")

        try:
            self._connection = redshift_connect(
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
            )
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to Redshift host={host}, "
                f"database={database}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the Redshift connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def read_source(
        self,
        source_name: str,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts.

        Redshift SUPER columns are returned as their native string
        representations. Downstream stages handle JSON parsing.
        """
        assert self._connection is not None, "Not connected. Call connect() first."
        cursor = self._connection.cursor()
        try:
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()

    def get_watermark(self, source_name: str) -> datetime | None:
        """Retrieve the last watermark for a source from asre_metadata."""
        assert self._connection is not None, "Not connected. Call connect() first."
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "SELECT value FROM asre_metadata WHERE key = %s",
                (f"watermark_{source_name}",),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return datetime.fromisoformat(str(row[0]))
        finally:
            cursor.close()

    def set_watermark(self, source_name: str, watermark: datetime) -> None:
        """Update the watermark for a source using DELETE + INSERT (Redshift lacks MERGE)."""
        assert self._connection is not None, "Not connected. Call connect() first."
        key = f"watermark_{source_name}"
        value = watermark.isoformat()
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "DELETE FROM asre_metadata WHERE key = %s",
                (key,),
            )
            cursor.execute(
                "INSERT INTO asre_metadata (key, value) VALUES (%s, %s)",
                (key, value),
            )
        finally:
            cursor.close()

    def execute_ddl(self, ddl: str) -> None:
        """Execute a DDL statement."""
        assert self._connection is not None, "Not connected. Call connect() first."
        cursor = self._connection.cursor()
        try:
            cursor.execute(ddl)
        finally:
            cursor.close()

    def write_records(
        self,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Write records to a table using INSERT.

        Dict and list values are JSON-serialized for SUPER columns.
        Uses schema-qualified table names.
        """
        if not records:
            return 0
        assert self._connection is not None, "Not connected. Call connect() first."

        columns = list(records[0].keys())
        col_list = ", ".join(columns)
        val_list = ", ".join(["%s"] * len(columns))
        qualified_table = f"{self._schema}.{table_name}" if self._schema else table_name
        stmt = f"INSERT INTO {qualified_table} ({col_list}) VALUES ({val_list})"

        cursor = self._connection.cursor()
        try:
            for record in records:
                params: dict[str, Any] = {}
                for col in columns:
                    val = record[col]
                    if isinstance(val, (dict, list)):
                        params[col] = json.dumps(val)
                    else:
                        params[col] = val
                cursor.execute(stmt, params)
        finally:
            cursor.close()

        return len(records)
