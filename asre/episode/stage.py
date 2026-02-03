"""Episode pipeline stages (US-095).

Three stages that integrate episode processing into the pipeline:
- EpisodeStitchStage: stitches encounters into episodes
- EpisodeMaterializeStage: writes episodes to asre_episodes, updates episode_id FK
- EpisodeQualityStage: computes episode-level metrics
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from asre.episode.episode_stitcher import EpisodeStitcher
from asre.episode.metadata_builder import EpisodeMetadataBuilder
from asre.models.batch import EventBatch
from asre.models.encounter import Encounter
from asre.models.episode import Episode
from asre.observability.metrics import StageMetrics
from asre.pipeline.runner import PipelineContext, PipelineStage

_ADMIT_EVENT_TYPES = {"ADMIT", "CLAIM_ADMIT", "ED_ARRIVAL", "OBS_START"}
_DISCHARGE_EVENT_TYPES = {"DISCHARGE", "CLAIM_DISCHARGE", "ED_DEPARTURE", "OBS_END"}

logger = logging.getLogger(__name__)

EPISODE_TABLE_NAME = "asre_episodes"


def _extract_source_type(source_system: str) -> str:
    """Extract source type prefix from source_system name."""
    lower = source_system.lower()
    for prefix in ("claims", "auth", "adt"):
        if lower.startswith(prefix):
            return prefix
    return lower


def scored_encounter_to_encounter(enc: Any) -> Encounter:
    """Convert a scored ReconciledEncounter to an Encounter dataclass.

    Extracts reconciled timestamps, classification, and scoring data into
    a flat Encounter for use by the episode stitcher.
    """
    now = datetime.now(tz=timezone.utc)

    # Get timestamps from reconciliation or events
    admit_ts: datetime | None = None
    discharge_ts: datetime | None = None
    admit_source_priority: str | None = None
    discharge_source_priority: str | None = None

    if hasattr(enc, "reconciled_timestamps") and enc.reconciled_timestamps is not None:
        admit_ts = enc.reconciled_timestamps.admit_ts
        discharge_ts = enc.reconciled_timestamps.discharge_ts
        admit_source_priority = enc.reconciled_timestamps.admit_source_priority
        discharge_source_priority = enc.reconciled_timestamps.discharge_source_priority
    else:
        # Derive from events
        for e in enc.events:
            if e.event_type in _ADMIT_EVENT_TYPES:
                if admit_ts is None or e.event_ts < admit_ts:
                    admit_ts = e.event_ts
            if e.event_type in _DISCHARGE_EVENT_TYPES:
                if discharge_ts is None or e.event_ts > discharge_ts:
                    discharge_ts = e.event_ts
        if admit_ts is None and enc.events:
            admit_ts = enc.events[0].event_ts

    # Classification
    encounter_type = "outpatient"
    drg: str | None = None
    payer_id: str | None = None
    principal_diagnosis: str | None = None
    diagnosis_codes: list[dict[str, Any]] | None = None

    if hasattr(enc, "reconciled_classification") and enc.reconciled_classification is not None:
        encounter_type = enc.reconciled_classification.encounter_type
        drg = enc.reconciled_classification.drg
        payer_id = enc.reconciled_classification.payer_id
        principal_diagnosis = enc.reconciled_classification.principal_diagnosis
        diagnosis_codes = enc.reconciled_classification.diagnosis_codes or None
    else:
        encounter_type = enc.encounter_type or "outpatient"

    # LOS
    los_hours: float | None = None
    if admit_ts is not None and discharge_ts is not None:
        delta = discharge_ts - admit_ts
        los_hours = delta.total_seconds() / 3600.0

    # Source info
    events = enc.events
    source_event_ids = [e.event_id for e in events]
    source_systems = list({e.source_system for e in events})
    source_types = {_extract_source_type(s) for s in source_systems}

    # Facility
    facility_canonical_id = enc.facility_canonical_id or ""
    is_acute = (encounter_type.lower() in ("inpatient", "ip"))

    return Encounter(
        encounter_id=enc.encounter_id,
        patient_key=enc.patient_key,
        encounter_type=encounter_type,
        status=enc.status,
        admit_ts=admit_ts or now,
        discharge_ts=discharge_ts,
        los_hours=los_hours,
        facility_canonical_id=facility_canonical_id,
        facility_name=facility_canonical_id,
        is_acute=is_acute,
        source_event_ids=source_event_ids,
        source_systems=source_systems,
        has_adt="adt" in source_types,
        has_claims="claims" in source_types,
        has_auth="auth" in source_types,
        confidence_score=enc.confidence_score,
        confidence_flags=enc.confidence_flags,
        created_at=now,
        updated_at=now,
        asre_version="0.1.0",
        drg=drg,
        payer_id=payer_id,
        principal_diagnosis=principal_diagnosis,
        diagnosis_codes=diagnosis_codes,
        admit_source_priority=admit_source_priority,
        discharge_source_priority=discharge_source_priority,
        obs_to_ip_conversion=enc.obs_to_ip_conversion,
        is_readmission=getattr(enc, "is_readmission", None),
        readmission_days=getattr(enc, "readmission_days", None),
    )


def _episode_to_record(episode: Episode) -> dict[str, Any]:
    """Convert an Episode dataclass to a flat dict for database storage."""
    return {
        "episode_id": episode.episode_id,
        "patient_key": episode.patient_key,
        "episode_type": episode.episode_type,
        "episode_status": episode.episode_status,
        "episode_start_ts": episode.episode_start_ts.isoformat() if episode.episode_start_ts else None,
        "episode_end_ts": episode.episode_end_ts.isoformat() if episode.episode_end_ts else None,
        "total_los_days": episode.total_los_days,
        "encounter_ids": json.dumps(episode.encounter_ids),
        "encounter_count": episode.encounter_count,
        "facility_count": episode.facility_count,
        "facility_sequence": json.dumps(episode.facility_sequence),
        "includes_readmission": episode.includes_readmission,
        "includes_post_acute": episode.includes_post_acute,
        "is_acute": episode.is_acute,
        "principal_diagnosis": episode.principal_diagnosis,
        "diagnosis_codes": json.dumps(episode.diagnosis_codes) if episode.diagnosis_codes else None,
        "confidence_score": episode.confidence_score,
        "created_at": episode.created_at.isoformat() if episode.created_at else None,
        "updated_at": episode.updated_at.isoformat() if episode.updated_at else None,
    }


class EpisodeStitchStage(PipelineStage):
    """Pipeline stage that stitches encounters into episodes.

    Uses EpisodeStitcher to group encounters by temporal and clinical
    linkage rules, then builds Episode objects via EpisodeMetadataBuilder.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("episode_stitch", "")
        self.encounters_in: list[Encounter] = []
        self.episodes: list[Episode] = []

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute episode stitching."""
        self.metrics = StageMetrics("episode_stitch", context.run_id)

        with self.metrics:
            encounters = list(self.encounters_in)
            self.metrics.records_in = len(encounters)

            if not encounters:
                self.episodes = []
                self.metrics.records_out = 0
                return batch

            # Build stitcher from config
            ep_cfg = context.config.get("episode_stitching", {})
            if hasattr(ep_cfg, "model_dump"):
                ep_cfg = ep_cfg.model_dump()
            elif not isinstance(ep_cfg, dict):
                ep_cfg = {}

            stitcher = EpisodeStitcher(
                readmission_window_days=ep_cfg.get("readmission_window_days", 30),
                post_acute_linkage_days=ep_cfg.get("post_acute_linkage_days", 14),
                planned_return_days=ep_cfg.get("planned_return_days", 90),
                ed_bounceback_days=ep_cfg.get("ed_bounceback_days", 7),
            )

            # Stitch into episode groups
            groups = stitcher.stitch(encounters)

            # Build Episode objects from groups
            builder = EpisodeMetadataBuilder()
            self.episodes = []
            for group in groups:
                episode = builder.build(
                    episode_id=group.episode_id,
                    encounters=group.encounters,
                    includes_readmission=group.includes_readmission,
                    includes_post_acute=group.includes_post_acute,
                )
                self.episodes.append(episode)

            self.metrics.records_out = len(self.episodes)

        return batch


class EpisodeMaterializeStage(PipelineStage):
    """Pipeline stage that writes episodes to asre_episodes table.

    Also updates the episode_id foreign key on encounters in
    admission_events_unified.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("episode_materialize", "")
        self.episodes_in: list[Episode] = []
        self.episodes_inserted: int = 0
        self.episodes_updated: int = 0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute episode materialization."""
        self.metrics = StageMetrics("episode_materialize", context.run_id)

        with self.metrics:
            episodes = list(self.episodes_in)
            self.metrics.records_in = len(episodes)

            adapter = context.config.get("adapter")
            if adapter is None:
                logger.warning(
                    "No adapter configured — skipping episode materialization"
                )
                self.metrics.records_out = 0
                return batch

            # Ensure table exists
            self._ensure_table(adapter)

            # Load existing episode_ids for upsert
            existing_ids = self._load_existing_ids(adapter)

            insert_records: list[dict[str, Any]] = []
            update_records: list[dict[str, Any]] = []

            now = datetime.now(tz=timezone.utc)

            for episode in episodes:
                record = _episode_to_record(episode)
                if record["episode_id"] in existing_ids:
                    # Preserve original created_at
                    record["created_at"] = existing_ids[record["episode_id"]]
                    record["updated_at"] = now.isoformat()
                    update_records.append(record)
                else:
                    insert_records.append(record)

            # Write inserts
            if insert_records:
                count: int = adapter.write_records(EPISODE_TABLE_NAME, insert_records)
                self.episodes_inserted = count

            # Write updates via DELETE + INSERT
            if update_records:
                for rec in update_records:
                    self._delete_by_id(adapter, rec["episode_id"])
                count = adapter.write_records(EPISODE_TABLE_NAME, update_records)
                self.episodes_updated = count

            # Update episode_id FK on encounters in admission_events_unified
            for episode in episodes:
                for encounter_id in episode.encounter_ids:
                    adapter.execute_ddl(
                        f"UPDATE admission_events_unified "
                        f"SET episode_id = '{episode.episode_id}' "
                        f"WHERE encounter_id = '{encounter_id}'"
                    )

            # Audit logging
            audit_logger = context.config.get("audit_logger")
            if audit_logger is not None:
                audit_entries: list[dict[str, str]] = []
                for rec in insert_records:
                    audit_entries.append({
                        "action": "materialize",
                        "entity_type": "episode",
                        "entity_id": rec["episode_id"],
                        "detail": (
                            f"Created episode: episode_type={rec['episode_type']}, "
                            f"encounter_count={rec['encounter_count']}"
                        ),
                    })
                for rec in update_records:
                    audit_entries.append({
                        "action": "materialize",
                        "entity_type": "episode",
                        "entity_id": rec["episode_id"],
                        "detail": (
                            f"Updated episode: episode_type={rec['episode_type']}, "
                            f"encounter_count={rec['encounter_count']}"
                        ),
                    })
                if audit_entries:
                    audit_logger.log_batch(audit_entries)

            self.metrics.records_out = self.episodes_inserted + self.episodes_updated

        return batch

    @staticmethod
    def _ensure_table(adapter: Any) -> None:
        """Create asre_episodes table if it does not exist."""
        ddl = (
            f"CREATE TABLE IF NOT EXISTS {EPISODE_TABLE_NAME} ("
            "episode_id TEXT PRIMARY KEY, "
            "patient_key TEXT NOT NULL, "
            "episode_type TEXT NOT NULL, "
            "episode_status TEXT NOT NULL, "
            "episode_start_ts TEXT, "
            "episode_end_ts TEXT, "
            "total_los_days REAL, "
            "encounter_ids TEXT, "
            "encounter_count INTEGER, "
            "facility_count INTEGER, "
            "facility_sequence TEXT, "
            "includes_readmission BOOLEAN, "
            "includes_post_acute BOOLEAN, "
            "is_acute BOOLEAN, "
            "principal_diagnosis TEXT, "
            "diagnosis_codes TEXT, "
            "confidence_score REAL, "
            "created_at TEXT, "
            "updated_at TEXT"
            ")"
        )
        adapter.execute_ddl(ddl)

    @staticmethod
    def _load_existing_ids(adapter: Any) -> dict[str, str]:
        """Load existing episode_ids and their created_at from the table."""
        try:
            rows: list[dict[str, Any]] = adapter.read_source(
                EPISODE_TABLE_NAME,
                f"SELECT episode_id, created_at FROM {EPISODE_TABLE_NAME}",
            )
            return {
                row["episode_id"]: row["created_at"] for row in rows
            }
        except Exception:
            return {}

    @staticmethod
    def _delete_by_id(adapter: Any, episode_id: str) -> None:
        """Delete a single episode by ID for upsert."""
        try:
            from sqlalchemy import text

            if hasattr(adapter, "_connection") and adapter._connection is not None:
                adapter._connection.execute(
                    text(f"DELETE FROM {EPISODE_TABLE_NAME} WHERE episode_id = :eid"),
                    {"eid": episode_id},
                )
                adapter._connection.commit()
        except Exception:
            pass


class EpisodeQualityStage(PipelineStage):
    """Pipeline stage that computes episode-level quality metrics.

    Tracks: episode_count, readmission_rate, mean_confidence.
    """

    def __init__(self) -> None:
        self.metrics: StageMetrics = StageMetrics("episode_quality", "")
        self.episodes_in: list[Episode] = []
        self.episode_count: int = 0
        self.readmission_rate: float = 0.0
        self.mean_confidence: float = 0.0

    def run(self, batch: EventBatch, context: PipelineContext) -> EventBatch:
        """Execute episode quality computation."""
        self.metrics = StageMetrics("episode_quality", context.run_id)

        with self.metrics:
            episodes = list(self.episodes_in)
            self.metrics.records_in = len(episodes)

            self.episode_count = len(episodes)

            if not episodes:
                self.readmission_rate = 0.0
                self.mean_confidence = 0.0
                self.metrics.records_out = 0
                return batch

            # Readmission rate
            readmission_count = sum(
                1 for ep in episodes if ep.includes_readmission
            )
            self.readmission_rate = readmission_count / len(episodes)

            # Mean confidence
            total_confidence = sum(ep.confidence_score for ep in episodes)
            self.mean_confidence = total_confidence / len(episodes)

            self.metrics.records_out = len(episodes)

        return batch
