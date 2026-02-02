"""IngestStage - pipeline stage for reading raw records from source tables."""

from __future__ import annotations

import logging
from typing import Any

from asre.ingest.dedup import dedup_by_source_record_id
from asre.ingest.query_builder import IngestQueryBuilder, resolve_lookback_buffer_hours
from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class IngestStage(PipelineStage):
    """Pipeline stage that reads raw records from all configured sources.

    Iterates over configured sources, builds queries based on mode
    (full/incremental), deduplicates by source_record_id, and collects
    raw record dicts for downstream canonicalization.
    """

    def __init__(self) -> None:
        self.raw_records: list[dict[str, Any]] = []
        self.metrics: StageMetrics = StageMetrics("ingest", "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the ingest stage across all configured sources.

        Args:
            batch: Input EventBatch (empty for ingest stage, first in pipeline).
            context: Pipeline context with config, mode, run_id.

        Returns:
            The same EventBatch (raw records stored on self.raw_records).
        """
        self.raw_records = []
        self.metrics = StageMetrics("ingest", context.run_id)

        sources: list[dict[str, Any]] = context.config.get("sources", [])
        adapter = context.config.get("adapter")
        schedule = context.config.get("schedule", {})
        lookback_config: dict[str, str] = schedule.get("lookback_buffer", {"default": "24h"})

        with self.metrics:
            for source_cfg in sources:
                self._ingest_source(source_cfg, adapter, context.mode, lookback_config)

            self.metrics.records_out = len(self.raw_records)

        return batch

    def _ingest_source(
        self,
        source_cfg: dict[str, Any],
        adapter: Any,
        mode: str,
        lookback_config: dict[str, str],
    ) -> None:
        """Ingest records from a single source."""
        source_name: str = source_cfg["name"]
        source_type: str = source_cfg["type"]
        source_def: dict[str, Any] = source_cfg["source"]
        field_mappings: dict[str, Any] = source_cfg.get("field_mappings", {})
        filters_cfg: dict[str, Any] | None = source_cfg.get("filters")

        table = source_def["table"]
        incremental_key = source_def["incremental_key"]
        source_record_id_field = field_mappings.get("source_record_id", "source_record_id")

        exclude_filter: str | None = None
        if filters_cfg and filters_cfg.get("exclude"):
            exclude_filter = filters_cfg["exclude"]

        # Get watermark for incremental mode
        watermark = None
        lookback_hours = 24
        if mode == "incremental":
            watermark = adapter.get_watermark(source_name)
            lookback_hours = resolve_lookback_buffer_hours(lookback_config, source_type)

        # Build query
        query_builder = IngestQueryBuilder(
            table=table,
            incremental_key=incremental_key,
            mode=mode,
            exclude_filter=exclude_filter,
            watermark=watermark,
            lookback_buffer_hours=lookback_hours,
        )
        query = query_builder.build_query()
        params = query_builder.build_params()

        try:
            records = adapter.read_source(source_name, query, params)
        except Exception:
            logger.exception("Failed to read source %s", source_name)
            self.metrics.errors += 1
            return

        self.metrics.records_in += len(records)

        # Dedup by source_record_id
        deduped, _dedup_count = dedup_by_source_record_id(records, source_record_id_field)

        # Annotate each record with metadata for downstream stages
        annotated: list[dict[str, Any]] = []
        for record in deduped:
            enriched = dict(record)
            enriched["_raw_payload"] = dict(record)
            enriched["_source_name"] = source_name
            enriched["_source_type"] = source_type
            annotated.append(enriched)

        self.raw_records.extend(annotated)

