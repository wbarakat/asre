"""Snowflake adapter implementing IngestAdapter using snowflake-connector-python."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

snowflake_connect: Any | None
try:
    from snowflake.connector import connect as _snowflake_connect

    snowflake_connect = _snowflake_connect
except ImportError:
    snowflake_connect = None

from asre.ingest.base import IngestAdapter


class SnowflakeAdapter(IngestAdapter):
    """Snowflake implementation of IngestAdapter.

    Uses snowflake-connector-python for database operations.
    Handles VARIANT type for JSON columns and ARRAY type for list columns.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._connection: Any = None

    @property
    def warehouse_type(self) -> str:
        return "snowflake"

    def connect(self) -> None:
        """Establish connection to Snowflake using config credentials."""
        if snowflake_connect is None:
            raise ImportError(
                "snowflake-connector-python is required for the Snowflake adapter. "
                "Install it with: pip install snowflake-connector-python"
            )

        account = self._config.get("account", "")
        user = self._config.get("user", "")
        password = self._config.get("password", "")
        database = self._config.get("database", "")
        schema = self._config.get("schema", "public")
        warehouse = self._config.get("warehouse", "")
        role = self._config.get("role")

        try:
            self._connection = snowflake_connect(
                account=account,
                user=user,
                password=password,
                database=database,
                schema=schema,
                warehouse=warehouse,
                role=role,
            )
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to Snowflake account={account}, "
                f"database={database}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the Snowflake connection."""
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

        Snowflake VARIANT and ARRAY columns are returned as their native
        string representations. Downstream stages handle JSON parsing.
        """
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
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
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
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
        """Update the watermark for a source in asre_metadata using MERGE."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        key = f"watermark_{source_name}"
        value = watermark.isoformat()
        cursor = self._connection.cursor()
        try:
            cursor.execute(
                "MERGE INTO asre_metadata AS target "
                "USING (SELECT %s AS key, %s AS value) AS source "
                "ON target.key = source.key "
                "WHEN MATCHED THEN UPDATE SET value = source.value "
                "WHEN NOT MATCHED THEN INSERT (key, value) VALUES (source.key, source.value)",
                (key, value),
            )
        finally:
            cursor.close()

    def execute_ddl(self, ddl: str) -> None:
        """Execute a DDL statement."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        cursor = self._connection.cursor()
        try:
            cursor.execute(ddl)
        finally:
            cursor.close()

    def execute_dml(self, statement: str, params: dict[str, Any] | None = None) -> None:
        """Execute a parameterized DML statement.

        Translates :name style parameters to Snowflake's %s style.
        """
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        cursor = self._connection.cursor()
        try:
            if params:
                import re
                ordered_keys: list[str] = []
                def _replace(match: re.Match[str]) -> str:
                    ordered_keys.append(match.group(1))
                    return "%s"
                translated = re.sub(r":(\w+)", _replace, statement)
                cursor.execute(translated, tuple(params[k] for k in ordered_keys))
            else:
                cursor.execute(statement)
        finally:
            cursor.close()

    def write_records(
        self,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Write records to a table using INSERT.

        Dict and list values are JSON-serialized for VARIANT/ARRAY columns.
        """
        if not records:
            return 0
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")

        columns = list(records[0].keys())
        col_list = ", ".join(columns)
        val_list = ", ".join(f"%({col})s" for col in columns)
        stmt = f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list})"

        cursor = self._connection.cursor()
        try:
            for record in records:
                params = {}
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
