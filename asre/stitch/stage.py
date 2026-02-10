"""StitchStage - pipeline stage for encounter stitching (US-052).

Processes EventBatch of canonical events and produces encounters using
EncounterStitcher. Builds encounter metadata for each stitched encounter.
Records stage metrics: events_in, encounters_out, transfers_detected,
cancellations_processed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from asre.models.batch import EventBatch
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage
from asre.stitch.encounter_stitcher import EncounterStitcher, StitchedEncounter
from asre.stitch.metadata import EncounterMetadata, build_encounter_metadata
from asre.canonicalize.store import CanonicalEventStore
from asre.canonicalize.timestamp_parser import parse_event_ts

logger = logging.getLogger(__name__)

# Cancellation event types tracked for metrics
_CANCELLATION_EVENT_TYPES = {"CANCEL_ADMIT", "CANCEL_DISCHARGE"}


class StitchStage(PipelineStage):
    """Pipeline stage that stitches canonical events into encounters.

    Uses EncounterStitcher to group events by patient, facility, and time window.
    Builds metadata for each encounter and tracks stage metrics.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("stitch", "")
        self.encounters: list[StitchedEncounter] = []
        self.encounter_metadata: list[EncounterMetadata] = []
        self.transfers_detected: int = 0
        self.cancellations_processed: int = 0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute the stitch stage.

        Args:
            batch: EventBatch containing canonical events to stitch.
            context: Pipeline context with run_id, config, and mode.

        Returns:
            The same EventBatch (encounters stored on stage.encounters).
        """
        self.metrics = StageMetrics("stitch", context.run_id)

        with self.metrics:
            events = self._load_history_events(batch.events, context)
            self.metrics.records_in = len(events)

            # Build stitcher from config
            stitcher = self._build_stitcher(context.config)

            # Stitch events into encounters
            self.encounters = stitcher.stitch(events)

            # Build metadata for each encounter
            self.encounter_metadata = [
                build_encounter_metadata(enc) for enc in self.encounters
            ]

            # Apply stable encounter_id mapping from history (incremental only)
            self._assign_stable_encounter_ids(self.encounters, context)

            # Count transfers
            self.transfers_detected = self._count_transfers(self.encounters)

            # Count cancellation events
            self.cancellations_processed = self._count_cancellations(batch.events)

            self.metrics.records_out = len(self.encounters)

        return batch

    def _load_history_events(
        self,
        events: list[Any],
        context: PipelineContext,
    ) -> list[Any]:
        """Load recent canonical events for affected patients in incremental runs."""
        if context.mode != "incremental":
            return events

        adapter = context.config.get("adapter")
        if adapter is None:
            return events

        stitch_cfg = context.config.get("encounter_stitching", {})
        use_history = True
        lookback_days = 90
        if isinstance(stitch_cfg, dict):
            use_history = stitch_cfg.get("use_canonical_history", True)
            lookback_days = stitch_cfg.get("history_lookback_days", 90)

        if not use_history or lookback_days <= 0:
            return events

        patient_keys = {e.patient_key for e in events if hasattr(e, "patient_key")}
        if not patient_keys:
            return events

        store = CanonicalEventStore(adapter)
        since_ts = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
        history = store.fetch_recent_events(patient_keys, since_ts=since_ts)

        combined: dict[str, Any] = {e.event_id: e for e in history}
        for event in events:
            combined[event.event_id] = event

        return list(combined.values())

    def _build_stitcher(self, config: dict[str, Any]) -> EncounterStitcher:
        """Build an EncounterStitcher from pipeline config.

        Reads encounter_stitching config section for time_window_hours,
        facility_must_match, same_timestamp_tiebreaker, patient_class_transitions.
        Uses defaults when config keys are missing.
        """
        stitch_config: dict[str, Any] = config.get("encounter_stitching", {})

        kwargs: dict[str, Any] = {}
        if "time_window_hours" in stitch_config:
            kwargs["time_window_hours"] = stitch_config["time_window_hours"]
        if "facility_must_match" in stitch_config:
            kwargs["facility_must_match"] = stitch_config["facility_must_match"]
        if "same_timestamp_tiebreaker" in stitch_config:
            kwargs["same_timestamp_tiebreaker"] = stitch_config[
                "same_timestamp_tiebreaker"
            ]
        if "patient_class_transitions" in stitch_config:
            kwargs["patient_class_transitions"] = stitch_config[
                "patient_class_transitions"
            ]

        return EncounterStitcher(**kwargs)

    def _assign_stable_encounter_ids(
        self,
        encounters: list[StitchedEncounter],
        context: PipelineContext,
    ) -> None:
        """Reuse encounter_ids from recent history to keep IDs stable."""
        if context.mode != "incremental":
            return

        adapter = context.config.get("adapter")
        if adapter is None:
            return

        stitch_cfg = context.config.get("encounter_stitching", {})
        use_history = True
        lookback_days = 90
        time_window_hours = 48
        facility_must_match = True
        if isinstance(stitch_cfg, dict):
            use_history = stitch_cfg.get("use_canonical_history", True)
            lookback_days = stitch_cfg.get("history_lookback_days", 90)
            time_window_hours = stitch_cfg.get("time_window_hours", 48)
            facility_must_match = stitch_cfg.get("facility_must_match", True)

        if not use_history or lookback_days <= 0:
            return

        patient_keys = {enc.patient_key for enc in encounters if enc.patient_key}
        if not patient_keys:
            return

        existing = self._load_recent_encounters(
            adapter,
            patient_keys,
            lookback_days=lookback_days,
        )
        if not existing:
            return

        by_patient: dict[str, list[_EncounterHistory]] = {}
        for rec in existing:
            by_patient.setdefault(rec.patient_key, []).append(rec)

        window = timedelta(hours=time_window_hours)
        for enc in encounters:
            candidates = by_patient.get(enc.patient_key, [])
            enc_start, enc_end = _encounter_range(enc)
            if enc_start is None:
                continue
            best: _EncounterHistory | None = None
            best_score: float | None = None
            for rec in candidates:
                rec_start = rec.start_ts
                if rec_start is None:
                    continue
                if facility_must_match and not _facility_match(
                    enc.facility_canonical_id, rec.facility_canonical_id
                ):
                    continue
                if not _ranges_overlap(enc_start, enc_end, rec_start, rec.end_ts, window):
                    continue
                score = abs((enc_start - rec_start).total_seconds())
                if best_score is None or score < best_score:
                    best = rec
                    best_score = score
            if best is not None:
                enc.encounter_id = best.encounter_id

    def _load_recent_encounters(
        self,
        adapter: Any,
        patient_keys: Iterable[str],
        *,
        lookback_days: int,
    ) -> list["_EncounterHistory"]:
        """Load recent encounters for patient keys from admission_events_unified."""
        keys = [k for k in patient_keys if k]
        if not keys:
            return []

        since_ts = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
        results: list[_EncounterHistory] = []
        for chunk in _chunk(keys, 500):
            keys_sql = ", ".join(_sql_literal(v) for v in chunk)
            query = (
                "SELECT encounter_id, patient_key, facility_canonical_id, "
                "admit_ts, discharge_ts, created_at, updated_at, status "
                f"FROM admission_events_unified WHERE patient_key IN ({keys_sql})"  # nosec B608
            )
            rows = adapter.read_source(
                "admission_events_unified",
                query,  # nosec B608
            )
            for row in rows:
                rec = _EncounterHistory.from_row(row)
                if rec.last_seen is None:
                    continue
                if rec.last_seen < since_ts:
                    continue
                results.append(rec)
        return results

    def _count_transfers(self, encounters: list[StitchedEncounter]) -> int:
        """Count the number of transfer chains detected.

        A transfer chain links 2+ encounters. We count unique chains,
        not individual encounters in chains.
        """
        seen_chains: set[tuple[int, ...]] = set()
        for enc in encounters:
            if enc.transfer_chain:
                chain_key = tuple(enc.transfer_chain)
                seen_chains.add(chain_key)
        return len(seen_chains)

    def _count_cancellations(self, events: list[Any]) -> int:
        """Count cancellation events (CANCEL_ADMIT, CANCEL_DISCHARGE)."""
        count = 0
        for event in events:
            if hasattr(event, "event_type") and event.event_type in _CANCELLATION_EVENT_TYPES:
                count += 1
        return count


@dataclass
class _EncounterHistory:
    encounter_id: str
    patient_key: str
    facility_canonical_id: str | None
    admit_ts: datetime | None
    discharge_ts: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    status: str | None

    @property
    def start_ts(self) -> datetime | None:
        return self.admit_ts or self.created_at or self.updated_at

    @property
    def end_ts(self) -> datetime | None:
        return self.discharge_ts or self.updated_at or self.admit_ts or self.created_at

    @property
    def last_seen(self) -> datetime | None:
        candidates = [
            ts for ts in (self.discharge_ts, self.updated_at, self.admit_ts, self.created_at) if ts is not None
        ]
        if not candidates:
            return None
        return max(candidates)

    @staticmethod
    def from_row(row: dict[str, Any]) -> "_EncounterHistory":
        return _EncounterHistory(
            encounter_id=str(row.get("encounter_id") or ""),
            patient_key=str(row.get("patient_key") or ""),
            facility_canonical_id=row.get("facility_canonical_id"),
            admit_ts=_parse_optional_ts(row.get("admit_ts")),
            discharge_ts=_parse_optional_ts(row.get("discharge_ts")),
            created_at=_parse_optional_ts(row.get("created_at")),
            updated_at=_parse_optional_ts(row.get("updated_at")),
            status=row.get("status"),
        )


def _parse_optional_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return parse_event_ts(value)
    except ValueError:
        return None


def _encounter_range(encounter: StitchedEncounter) -> tuple[datetime | None, datetime | None]:
    if not encounter.events:
        return None, None
    event_ts = [e.event_ts for e in encounter.events]
    start = min(event_ts)
    end = max(event_ts)
    return start, end


def _ranges_overlap(
    start_a: datetime,
    end_a: datetime | None,
    start_b: datetime | None,
    end_b: datetime | None,
    window: timedelta,
) -> bool:
    if start_b is None:
        return False
    end_a = end_a or start_a
    end_b = end_b or start_b
    return start_a <= end_b + window and end_a + window >= start_b


def _facility_match(
    facility_a: str | None,
    facility_b: str | None,
) -> bool:
    if facility_a is None or facility_b is None:
        return False
    return facility_a == facility_b


def _chunk(values: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _sql_literal(value: str) -> str:
    escaped = value.replace("'", "''")
    return f"'{escaped}'"
