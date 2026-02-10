"""FacilityNormalizationStage - pipeline stage for facility name resolution.

Processes each canonical event: normalizes facility_raw, matches against
known facilities (exact alias, NPI, CCN, fuzzy), and sets facility_canonical_id.
Updates facility registry with any new facilities created during resolution.
"""

from __future__ import annotations

import logging
from typing import Any

from asre.config.facility_alias_schema import FacilityAliasConfig
from asre.canonicalize.store import CanonicalEventStore
from asre.facility.matcher import FacilityMatcher, MatchResult
from asre.facility.normalizer import FacilityNormalizer
from asre.facility.registry import FacilityRegistry
from asre.models.batch import EventBatch
from asre.models.canonical_event import CanonicalEvent
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class FacilityNormalizationStage(PipelineStage):
    """Pipeline stage that resolves facility names to canonical IDs.

    For each canonical event, normalizes facility_raw, matches against
    the facility registry, and sets facility_canonical_id. Unresolved
    facilities are created as new entries flagged for review.
    """

    def __init__(
        self,
        normalizer: FacilityNormalizer,
        alias_config: FacilityAliasConfig,
        registry: FacilityRegistry,
        fuzzy_threshold: float = 0.85,
        sqlite_lookup: Any | None = None,
    ) -> None:
        self._normalizer = normalizer
        self._alias_config = alias_config
        self._registry = registry
        self._sqlite_lookup = sqlite_lookup
        self._matcher = FacilityMatcher(
            alias_config=alias_config,
            normalizer=normalizer,
            fuzzy_threshold=fuzzy_threshold,
            sqlite_lookup=sqlite_lookup,
        )
        self.metrics: StageMetrics = StageMetrics("facility_normalize", "")

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the facility normalization stage.

        Args:
            batch: EventBatch containing canonical events with facility_raw set.
            context: Pipeline context with run_id and config.

        Returns:
            The same EventBatch with facility_canonical_id populated on events.
        """
        self.metrics = StageMetrics("facility_normalize", context.run_id)
        audit_entries: list[dict[str, str]] = []

        with self.metrics:
            self.metrics.records_in = len(batch.events)

            for event in batch.events:
                self._resolve_facility(event)
                entity_id = (
                    event.facility_canonical_id
                    or event.facility_raw
                    or ""
                )
                if event.facility_match_type == "new":
                    audit_entries.append({
                        "action": "normalize",
                        "entity_type": "facility",
                        "entity_id": entity_id,
                        "detail": f"New facility created: {event.facility_raw} -> {event.facility_canonical_id}, flagged FACILITY_NEW_UNREVIEWED",
                    })
                elif event.facility_match_type == "fuzzy":
                    audit_entries.append({
                        "action": "normalize",
                        "entity_type": "facility",
                        "entity_id": entity_id,
                        "detail": f"Fuzzy match: {event.facility_raw} -> {event.facility_canonical_id}",
                    })

            # Flush facility audit entries
            audit_logger = context.config.get("audit_logger")
            if audit_logger is not None and audit_entries:
                audit_logger.log_batch(audit_entries)

            # Persist canonical events for history lookback
            adapter = context.config.get("adapter")
            stitch_cfg = context.config.get("encounter_stitching", {})
            use_history = True
            if isinstance(stitch_cfg, dict):
                use_history = stitch_cfg.get("use_canonical_history", True)
            if adapter is not None and use_history:
                store = CanonicalEventStore(adapter)
                store.upsert_events(batch.events)

            # Persist facility registry (skip in dry-run)
            if adapter is not None and not context.config.get("dry_run", False):
                self._ensure_registry_table(adapter)
                self._registry.upsert(adapter)

            self.metrics.records_out = len(batch.events)

        return batch

    def _resolve_facility(self, event: CanonicalEvent) -> None:
        """Resolve a single event's facility_raw to facility_canonical_id.

        Uses FacilityMatcher.resolve_or_create() which cascades through:
        exact alias -> NPI -> CCN -> fuzzy -> create new.

        New facilities are added to the registry.
        """
        facility_raw = event.facility_raw
        if not facility_raw or not facility_raw.strip():
            return

        # Extract NPI/CCN from mapped fields, fall back to raw payload
        npi: str | None = event.npi
        ccn: str | None = event.ccn
        if event._raw_payload:
            npi = npi or event._raw_payload.get("npi")
            ccn = ccn or event._raw_payload.get("ccn")

        result = self._matcher.resolve_or_create(
            facility_name=facility_raw,
            npi=npi,
            ccn=ccn,
        )

        if result is None:
            return

        event.facility_canonical_id = result.canonical_id
        event.facility_match_type = result.match_type

        # If a new facility was created, register it in the registry
        if result.match_type == "new":
            normalized_name = self._normalizer.normalize(facility_raw)
            self._registry.add_facility(
                canonical_id=result.canonical_id,
                canonical_name=facility_raw,
                aliases=[normalized_name] if normalized_name else [],
                flags=list(result.flags),
            )
            logger.info(
                "New facility created: %s (%s) - flagged %s",
                result.canonical_id,
                facility_raw,
                result.flags,
            )
        elif result.match_type in ("npi_registry", "ccn_registry"):
            # SQLite registry hit — add to in-memory registry so it gets
            # persisted to asre_facility_registry for customer visibility
            if not self._registry.get_facility(result.canonical_id):
                self._registry.add_facility(
                    canonical_id=result.canonical_id,
                    canonical_name=facility_raw,
                    npi=npi,
                    ccn=ccn,
                )
            logger.debug(
                "Facility resolved via %s: %s -> %s",
                result.match_type,
                facility_raw,
                result.canonical_id,
            )
        else:
            logger.debug(
                "Facility resolved: %s -> %s (match_type=%s, score=%.2f)",
                facility_raw,
                result.canonical_id,
                result.match_type,
                result.score,
            )

    @staticmethod
    def _ensure_registry_table(adapter: Any) -> None:
        """Create the asre_facility_registry table if it doesn't exist."""
        from asre.migration.ddl_types import DDLTypeMapper, add_column_if_missing

        wt = getattr(adapter, "warehouse_type", "postgres")
        m = DDLTypeMapper(wt)
        t = m.text()
        j = m.json()
        pk = m.primary_key("canonical_id")

        cols = [
            pk,
            f"canonical_name {t} NOT NULL",
            f"npi {t}",
            f"ccn {t}",
            f"facility_type {t}",
            f"aliases {j}",
            f"flags {j}",
            f"address {t}",
        ]
        col_str = ", ".join(cols)
        adapter.execute_ddl(
            f"CREATE TABLE IF NOT EXISTS asre_facility_registry ({col_str})"
        )

        # Ensure columns added by later migrations exist on older installs
        add_column_if_missing(adapter, "asre_facility_registry", "address", t)
