"""BigQuery adapter implementing IngestAdapter using google-cloud-bigquery."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, cast

BigQueryClient: Any
QueryJobConfig: Any
ScalarQueryParameter: Any
try:
    from google.cloud.bigquery import (
        Client as _BigQueryClient,
        QueryJobConfig as _QueryJobConfig,
        ScalarQueryParameter as _ScalarQueryParameter,
    )

    BigQueryClient = _BigQueryClient
    QueryJobConfig = _QueryJobConfig
    ScalarQueryParameter = _ScalarQueryParameter
    _HAS_BIGQUERY = True
except ImportError:
    BigQueryClient = None
    QueryJobConfig = None
    ScalarQueryParameter = None
    _HAS_BIGQUERY = False

from asre.ingest.base import IngestAdapter


class BigQueryAdapter(IngestAdapter):
    """BigQuery implementation of IngestAdapter.

    Uses google-cloud-bigquery for database operations.
    Handles STRUCT/JSON types for complex columns and ARRAY type for list columns.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config
        self._client: Any = None
        self._dataset: str = config.get("dataset", "")
        self._project: str = config.get("project", "")

    @property
    def warehouse_type(self) -> str:
        return "bigquery"

    def connect(self) -> None:
        """Establish connection to BigQuery using config credentials."""
        if not _HAS_BIGQUERY:
            raise ImportError(
                "google-cloud-bigquery is required for the BigQuery adapter. "
                "Install it with: pip install google-cloud-bigquery"
            )

        project = self._config.get("project", "")
        location = self._config.get("location", "US")
        credentials_path = self._config.get("credentials_path")

        try:
            kwargs: dict[str, Any] = {"project": project, "location": location}
            api_endpoint = self._config.get("api_endpoint")
            if api_endpoint:
                from google.api_core.client_options import ClientOptions
                from google.auth.credentials import AnonymousCredentials

                kwargs["client_options"] = ClientOptions(api_endpoint=api_endpoint)
                kwargs["credentials"] = AnonymousCredentials()
            elif credentials_path:
                from google.oauth2 import service_account

                credentials_cls = cast(Any, service_account.Credentials)
                credentials = credentials_cls.from_service_account_file(credentials_path)
                kwargs["credentials"] = credentials
            self._client = BigQueryClient(**kwargs)
        except Exception as exc:
            raise ConnectionError(
                f"Failed to connect to BigQuery project={project}: {exc}"
            ) from exc

    def disconnect(self) -> None:
        """Close the BigQuery client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _make_job_config(
        self, parameters: list[tuple[str, str, Any]]
    ) -> Any:
        """Create a QueryJobConfig with scalar query parameters."""
        return QueryJobConfig(
            query_parameters=[
                ScalarQueryParameter(name, ptype, val)
                for name, ptype, val in parameters
            ]
        )

    @staticmethod
    def _validate_identifier(value: str, label: str) -> str:
        """Ensure BigQuery identifiers are restricted to safe characters."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
            raise ValueError(f"Invalid BigQuery {label}: {value!r}")
        return value

    def read_source(
        self,
        source_name: str,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SELECT query and return results as list of dicts.

        BigQuery STRUCT/JSON and ARRAY columns are returned as their native
        Python representations (dicts and lists). Downstream stages handle
        further processing.
        """
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        if params:
            translated = re.sub(r":(\w+)", r"@\1", query)
            job_config = self._make_job_config(
                [(k, "STRING", str(v)) for k, v in params.items()]
            )
            query_job = self._client.query(translated, job_config=job_config)
        else:
            query_job = self._client.query(query)

        rows = query_job.result()
        return [dict(row) for row in rows]

    def get_watermark(self, source_name: str) -> datetime | None:
        """Retrieve the last watermark for a source from asre_metadata."""
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")
        dataset = self._validate_identifier(self._config.get("dataset", ""), "dataset")
        query = (
            f"SELECT value FROM `{dataset}.asre_metadata` "  # nosec B608
            f"WHERE key = @key"
        )
        job_config = self._make_job_config(
            [("key", "STRING", f"watermark_{source_name}")]
        )
        query_job = self._client.query(query, job_config=job_config)
        results = list(query_job.result())
        if not results:
            return None
        return datetime.fromisoformat(str(results[0]["value"]))

    def set_watermark(self, source_name: str, watermark: datetime) -> None:
        """Update the watermark for a source in asre_metadata using MERGE."""
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")
        dataset = self._validate_identifier(self._config.get("dataset", ""), "dataset")
        key = f"watermark_{source_name}"
        value = watermark.isoformat()
        query = (
            f"MERGE `{dataset}.asre_metadata` AS target "  # nosec B608
            f"USING (SELECT @key AS key, @value AS value) AS source "
            f"ON target.key = source.key "
            f"WHEN MATCHED THEN UPDATE SET value = source.value "
            f"WHEN NOT MATCHED THEN INSERT (key, value) VALUES (source.key, source.value)"
        )
        job_config = self._make_job_config(
            [("key", "STRING", key), ("value", "STRING", value)]
        )
        query_job = self._client.query(query, job_config=job_config)
        query_job.result()  # Wait for completion

    def execute_ddl(self, ddl: str) -> None:
        """Execute a DDL statement."""
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")
        query_job = self._client.query(ddl)
        query_job.result()  # Wait for completion

    def qualify_table(self, table_name: str) -> str:
        """Return a dataset-qualified, backtick-wrapped table name for BigQuery."""
        dataset = self._validate_identifier(self._dataset, "dataset")
        return f"`{dataset}.{table_name}`"

    def execute_dml(self, statement: str, params: dict[str, Any] | None = None) -> None:
        """Execute a parameterized DML statement.

        Translates :name style parameters to BigQuery's @name style.
        """
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")
        if params:
            translated = re.sub(r":(\w+)", r"@\1", statement)
            job_config = self._make_job_config(
                [(k, "STRING", str(v)) for k, v in params.items()]
            )
            query_job = self._client.query(translated, job_config=job_config)
        else:
            query_job = self._client.query(statement)
        query_job.result()

    def write_records(
        self,
        table_name: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Write records to a table using INSERT DML.

        Dict and list values are JSON-serialized for JSON/ARRAY columns.
        """
        if not records:
            return 0
        if self._client is None:
            raise RuntimeError("Not connected. Call connect() first.")

        dataset = self._validate_identifier(self._config.get("dataset", ""), "dataset")
        table_name = self._validate_identifier(table_name, "table name")
        columns = list(records[0].keys())
        col_list = ", ".join(columns)

        for record in records:
            values: list[str] = []
            for col in columns:
                val = record[col]
                if val is None:
                    values.append("NULL")
                elif isinstance(val, (dict, list)):
                    json_str = json.dumps(val).replace("'", "\\'")
                    values.append(f"JSON '{json_str}'")
                elif isinstance(val, bool):
                    values.append("TRUE" if val else "FALSE")
                elif isinstance(val, (int, float)):
                    values.append(str(val))
                elif isinstance(val, datetime):
                    values.append(f"TIMESTAMP '{val.isoformat()}'")
                else:
                    escaped = str(val).replace("'", "\\'")
                    values.append(f"'{escaped}'")
            val_list = ", ".join(values)
            query = (
                f"INSERT INTO `{dataset}.{table_name}` ({col_list}) VALUES ({val_list})"  # nosec B608
            )
            query_job = self._client.query(query)
            query_job.result()

        return len(records)
