"""Abstract base class for warehouse ingest adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class IngestAdapter(ABC):
    """Abstract adapter interface for warehouse implementations.

    All warehouse-specific adapters (Postgres, Snowflake, BigQuery, Redshift)
    must implement this interface to be used by the ingest pipeline stage.
    """

    @property
    @abstractmethod
    def warehouse_type(self) -> str:
        """Return the warehouse type identifier (e.g., 'postgres', 'snowflake')."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the warehouse."""

    @abstractmethod
    def disconnect(self) -> None:
        """Close the warehouse connection."""

    @abstractmethod
    def read_source(
        self,
        source_name: str,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Read records from a source table.

        Args:
            source_name: Logical name of the source.
            query: SQL query to execute.
            params: Optional query parameters.

        Returns:
            List of records as dicts.
        """

    @abstractmethod
    def get_watermark(self, source_name: str) -> datetime | None:
        """Retrieve the last watermark for a source.

        Args:
            source_name: Logical name of the source.

        Returns:
            Last watermark timestamp, or None if no watermark exists.
        """

    @abstractmethod
    def set_watermark(self, source_name: str, watermark: datetime) -> None:
        """Update the watermark for a source.

        Args:
            source_name: Logical name of the source.
            watermark: New watermark timestamp.
        """

    @abstractmethod
    def execute_ddl(self, ddl: str) -> None:
        """Execute a DDL statement (CREATE TABLE, ALTER, etc.).

        Args:
            ddl: The DDL statement to execute.
        """

    @abstractmethod
    def execute_dml(self, statement: str, params: dict[str, Any] | None = None) -> None:
        """Execute a DML statement (UPDATE, DELETE, INSERT) with parameters.

        Args:
            statement: The DML statement with named parameter placeholders.
            params: Parameter values for the statement.
        """

    @abstractmethod
    def write_records(
        self,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Write records to a table.

        Args:
            table_name: Target table name.
            records: List of records as dicts.

        Returns:
            Number of records written.
        """
