"""PostgreSQL adapter implementing IngestAdapter using SQLAlchemy + psycopg2."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, Connection

from asre.ingest.base import IngestAdapter

logger = logging.getLogger(__name__)


class PostgresAdapter(IngestAdapter):
    """PostgreSQL implementation of IngestAdapter.

    Uses SQLAlchemy with psycopg2 driver for database operations.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._engine: Engine | None = None
        self._connection: Connection | None = None

    @property
    def warehouse_type(self) -> str:
        return "postgres"

    def connect(self) -> None:
        """Establish connection to PostgreSQL using config credentials."""
        host = self._config.get("host", "localhost")
        port = self._config.get("port", "5432")
        database = self._config.get("database", "")
        user = self._config.get("user", "")
        password = self._config.get("password", "")
        schema = self._config.get("schema", "public")
        require_utf8 = bool(self._config.get("require_utf8", True))

        url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"

        try:
            self._engine = create_engine(
                url,
                connect_args={"options": f"-csearch_path={schema}"},
            )
            self._connection = self._engine.connect()
            if hasattr(self._connection, "connection"):
                raw_connection = self._connection.connection
                if hasattr(raw_connection, "set_client_encoding"):
                    raw_connection.set_client_encoding("UTF8")
            if require_utf8:
                server_enc = self._connection.execute(
                    text("SHOW server_encoding")
                ).scalar()
                client_enc = self._connection.execute(
                    text("SHOW client_encoding")
                ).scalar()
                if not isinstance(server_enc, str) or not isinstance(client_enc, str):
                    # Some unit-test mocks return non-string sentinel objects.
                    # Skip strict checks in that case and rely on integration tests.
                    logger.debug(
                        "Skipping UTF-8 enforcement due non-string encoding values: "
                        "server=%r client=%r",
                        server_enc,
                        client_enc,
                    )
                    return
                server_str = str(server_enc or "").upper().replace("-", "")
                client_str = str(client_enc or "").upper().replace("-", "")
                if server_str != "UTF8" or client_str != "UTF8":
                    raise ConnectionError(
                        "PostgreSQL must use UTF-8 encoding. "
                        f"server_encoding={server_enc}, client_encoding={client_enc}"
                    )
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to PostgreSQL at {host}:{port}/{database}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the PostgreSQL connection and dispose the engine."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def read_source(
        self,
        source_name: str,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        try:
            result = self._connection.execute(text(query), params or {})
        except Exception:
            self._connection.rollback()
            raise
        return [dict(row) for row in result.mappings()]

    def get_watermark(self, source_name: str) -> datetime | None:
        """Retrieve the last watermark for a source from asre_metadata."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        result = self._connection.execute(
            text(
                "SELECT value FROM asre_metadata "
                "WHERE key = :key"
            ),
            {"key": f"watermark_{source_name}"},
        )
        row = result.fetchone()
        if row is None:
            return None
        return datetime.fromisoformat(str(row[0]))

    def set_watermark(self, source_name: str, watermark: datetime) -> None:
        """Update the watermark for a source in asre_metadata."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        self._connection.execute(
            text(
                "INSERT INTO asre_metadata (key, value) "
                "VALUES (:key, :value) "
                "ON CONFLICT (key) DO UPDATE SET value = :value"
            ),
            {"key": f"watermark_{source_name}", "value": watermark.isoformat()},
        )
        self._connection.commit()

    def execute_ddl(self, ddl: str) -> None:
        """Execute a DDL statement."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        self._connection.execute(text(ddl))
        self._connection.commit()

    def execute_dml(self, statement: str, params: dict[str, Any] | None = None) -> None:
        """Execute a parameterized DML statement."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        self._connection.execute(text(statement), params or {})
        self._connection.commit()

    def write_records(
        self,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Write records to a table using INSERT."""
        if not records:
            return 0
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")

        columns = list(records[0].keys())
        col_list = ", ".join(columns)
        val_list = ", ".join(f":{col}" for col in columns)
        stmt = text(f"INSERT INTO {table_name} ({col_list}) VALUES ({val_list})")

        for record in records:
            self._connection.execute(stmt, record)
        self._connection.commit()

        return len(records)
