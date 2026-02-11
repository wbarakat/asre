"""Integration test fixtures with parametrized adapter support.

Provides adapter fixtures for Postgres, BigQuery (emulator), and Redshift
(redshift-connector against Postgres). Adapters that fail to connect are
skipped gracefully.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Generator
from typing import Any
from urllib.parse import urlparse

import pytest

from asre.ingest.base import IngestAdapter
from asre.ingest.postgres import PostgresAdapter


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """Quick TCP check to avoid long hangs when a service is down."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _pg_config() -> dict[str, str]:
    """Build Postgres config from env vars with sensible defaults."""
    return {
        "host": os.environ.get("ASRE_TEST_PG_HOST", "localhost"),
        "port": os.environ.get("ASRE_TEST_PG_PORT", "5432"),
        "database": os.environ.get("ASRE_TEST_PG_DATABASE", "asre_test"),
        "user": os.environ.get("ASRE_TEST_PG_USER", "postgres"),
        "password": os.environ.get("ASRE_TEST_PG_PASSWORD", "postgres"),
        "schema": os.environ.get("ASRE_TEST_PG_SCHEMA", "public"),
    }


def _try_postgres() -> PostgresAdapter | None:
    """Try to connect a PostgresAdapter, return None on failure."""
    adapter = PostgresAdapter(_pg_config())
    try:
        adapter.connect()
        return adapter
    except (ConnectionError, Exception):
        return None


def _try_bigquery() -> Any | None:
    """Try to connect a BigQueryAdapter to the emulator, return None on failure."""
    try:
        from asre.ingest.bigquery import BigQueryAdapter
    except ImportError:
        return None

    endpoint = os.environ.get("ASRE_TEST_BQ_ENDPOINT", "http://localhost:9050")
    # Quick TCP probe to avoid long hangs when emulator is not running
    parsed = urlparse(endpoint)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9050
    if not _port_open(host, port):
        return None

    config = {
        "project": os.environ.get("ASRE_TEST_BQ_PROJECT", "test"),
        "dataset": os.environ.get("ASRE_TEST_BQ_DATASET", "test"),
        "api_endpoint": endpoint,
        "location": "US",
    }
    adapter = BigQueryAdapter(config)
    try:
        adapter.connect()
        return adapter
    except (ConnectionError, ImportError, Exception):
        return None


def _try_redshift() -> Any | None:
    """Try to connect a RedshiftAdapter to a Postgres stand-in, return None on failure.

    Uses psycopg2 under the hood (via PostgresAdapter) because
    redshift-connector sends Redshift-specific startup parameters
    (client_protocol_version, driver_version) that vanilla Postgres
    rejects. The RedshiftAdapter is then monkey-patched to use this
    connection while preserving its warehouse_type and DML translation.
    """
    try:
        from asre.ingest.redshift import RedshiftAdapter
    except ImportError:
        return None

    host = os.environ.get("ASRE_TEST_RS_HOST", "localhost")
    port = int(os.environ.get("ASRE_TEST_RS_PORT", "5434"))
    if not _port_open(host, port):
        return None

    # Connect via psycopg2 (same as PostgresAdapter) to avoid
    # redshift-connector's incompatible startup handshake with vanilla PG.
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=host,
            port=port,
            dbname=os.environ.get("ASRE_TEST_RS_DATABASE", "asre_test"),
            user=os.environ.get("ASRE_TEST_RS_USER", "asre_test"),
            password=os.environ.get("ASRE_TEST_RS_PASSWORD", "asre_test"),
        )
        conn.autocommit = True
    except Exception:
        return None

    config: dict[str, Any] = {
        "host": host,
        "port": port,
        "database": os.environ.get("ASRE_TEST_RS_DATABASE", "asre_test"),
        "user": os.environ.get("ASRE_TEST_RS_USER", "asre_test"),
        "password": os.environ.get("ASRE_TEST_RS_PASSWORD", "asre_test"),
        "schema": os.environ.get("ASRE_TEST_RS_SCHEMA", "public"),
        "ssl": False,
    }
    adapter = RedshiftAdapter(config)
    # Inject the psycopg2 connection instead of redshift-connector's
    adapter._connection = conn
    return adapter


_ADAPTER_FACTORIES = {
    "postgres": _try_postgres,
    "bigquery": _try_bigquery,
    "redshift": _try_redshift,
}


@pytest.fixture(params=["postgres", "bigquery", "redshift"])
def adapter(request: pytest.FixtureRequest) -> Generator[IngestAdapter, None, None]:
    """Parametrized adapter fixture — runs each test against all 3 warehouses.

    Skips gracefully when a warehouse is unavailable.
    """
    name = request.param
    factory = _ADAPTER_FACTORIES[name]
    instance = factory()
    if instance is None:
        pytest.skip(f"{name} adapter not available")
    yield instance
    instance.disconnect()


@pytest.fixture
def pg_adapter() -> Generator[PostgresAdapter, None, None]:
    """Standalone Postgres adapter for existing integration tests."""
    instance = _try_postgres()
    if instance is None:
        pytest.skip("PostgreSQL not available for integration tests")
    assert instance is not None
    yield instance
    instance.disconnect()
