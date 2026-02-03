"""BigQuery adapter implementing IngestAdapter using google-cloud-bigquery."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

try:
    from google.cloud.bigquery import (
        Client as BigQueryClient,
        QueryJobConfig,
        ScalarQueryParameter,
    )

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
            if credentials_path:
                from google.oauth2 import service_account

                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path
                )
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
        assert self._client is not None, "Not connected. Call connect() first."

        if params:
            job_config = self._make_job_config(
                [(k, "STRING", str(v)) for k, v in params.items()]
            )
            query_job = self._client.query(query, job_config=job_config)
        else:
            query_job = self._client.query(query)

        rows = query_job.result()
        return [dict(row) for row in rows]

    def get_watermark(self, source_name: str) -> datetime | None:
        """Retrieve the last watermark for a source from asre_metadata."""
        assert self._client is not None, "Not connected. Call connect() first."
        dataset = self._config.get("dataset", "")
        query = (
            f"SELECT value FROM `{dataset}.asre_metadata` "
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
        assert self._client is not None, "Not connected. Call connect() first."
        dataset = self._config.get("dataset", "")
        key = f"watermark_{source_name}"
        value = watermark.isoformat()
        query = (
            f"MERGE `{dataset}.asre_metadata` AS target "
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
        assert self._client is not None, "Not connected. Call connect() first."
        query_job = self._client.query(ddl)
        query_job.result()  # Wait for completion

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
        assert self._client is not None, "Not connected. Call connect() first."

        dataset = self._config.get("dataset", "")
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
            query = f"INSERT INTO `{dataset}.{table_name}` ({col_list}) VALUES ({val_list})"
            query_job = self._client.query(query)
            query_job.result()

        return len(records)
