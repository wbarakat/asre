"""Cross-warehouse DDL type mapping for migrations."""

from __future__ import annotations

import logging
from typing import Protocol

# Type mapping per warehouse: generic_name -> warehouse-specific SQL type
_TYPE_MAP: dict[str, dict[str, str]] = {
    "postgres": {
        "text": "TEXT",
        "boolean": "BOOLEAN",
        "integer": "INTEGER",
        "real": "REAL",
        "json": "JSONB",
        "array": "JSONB",
        "timestamp": "TIMESTAMPTZ",
    },
    "snowflake": {
        "text": "TEXT",
        "boolean": "BOOLEAN",
        "integer": "INTEGER",
        "real": "REAL",
        "json": "VARIANT",
        "array": "ARRAY",
        "timestamp": "TIMESTAMP_TZ",
    },
    "bigquery": {
        "text": "STRING",
        "boolean": "BOOL",
        "integer": "INT64",
        "real": "FLOAT64",
        "json": "JSON",
        "array": "JSON",
        "timestamp": "TIMESTAMP",
    },
    "redshift": {
        "text": "VARCHAR(65535)",
        "boolean": "BOOLEAN",
        "integer": "INTEGER",
        "real": "REAL",
        "json": "SUPER",
        "array": "SUPER",
        "timestamp": "TIMESTAMPTZ",
    },
}

logger = logging.getLogger(__name__)


class DDLTypeMapper:
    """Maps generic column types to warehouse-specific SQL types.

    Defaults to Postgres types for unknown warehouse types.
    """

    def __init__(self, warehouse_type: str) -> None:
        self._warehouse_type = warehouse_type
        self._types = _TYPE_MAP.get(warehouse_type, _TYPE_MAP["postgres"])

    @property
    def warehouse_type(self) -> str:
        return self._warehouse_type

    def text(self) -> str:
        return self._types["text"]

    def boolean(self) -> str:
        return self._types["boolean"]

    def integer(self) -> str:
        return self._types["integer"]

    def real(self) -> str:
        return self._types["real"]

    def json(self) -> str:
        return self._types["json"]

    def array(self) -> str:
        return self._types["array"]

    def timestamp(self) -> str:
        return self._types["timestamp"]

    def primary_key(self, column: str) -> str:
        """Generate single-column primary key DDL.

        BigQuery doesn't support PRIMARY KEY constraints in CREATE TABLE.
        """
        if self._warehouse_type == "bigquery":
            return f"{column} {self.text()} NOT NULL"
        return f"{column} {self.text()} PRIMARY KEY"

    def composite_primary_key(self, columns: list[str]) -> str:
        """Generate composite primary key DDL.

        BigQuery doesn't support composite PK constraints.
        Returns empty string for BigQuery.
        """
        if self._warehouse_type == "bigquery":
            return ""
        return f"PRIMARY KEY ({', '.join(columns)})"


class DDLExecutor(Protocol):
    """Protocol for adapters that can execute DDL."""

    def execute_ddl(self, ddl: str) -> None: ...


def add_column_if_missing(
    adapter: DDLExecutor,
    table: str,
    column: str,
    col_type: str,
) -> None:
    """Attempt to add a column to a table, ignoring errors if it already exists.

    This is used by _ensure_table() methods as a safety net to converge
    existing installs to the latest schema, even if migrations haven't run.
    """
    try:
        adapter.execute_ddl(
            f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
        )  # nosec B608
    except Exception as exc:
        logger.debug(
            "Skipping add-column safety net for %s.%s: %s",
            table,
            column,
            exc,
        )
