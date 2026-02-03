"""003: Create output tables for ASRE pipeline (US-080).

Creates the 5 output tables:
- admission_events_unified: Primary encounter-level unified view
- asre_encounters_detail: Event-level detail with role classifications
- asre_audit_log: All pipeline modifications for audit
- asre_run_metrics: Per-stage timing and throughput metrics
- asre_quality_metrics: Per-run quality metrics with pass/warn/fail status
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asre.ingest.base import IngestAdapter

description = "output tables"


def upgrade(adapter: IngestAdapter) -> None:
    """Create all 5 ASRE output tables."""
    _create_admission_events_unified(adapter)
    _create_asre_encounters_detail(adapter)
    _create_asre_audit_log(adapter)
    _create_asre_run_metrics(adapter)
    _create_asre_quality_metrics(adapter)


def _create_admission_events_unified(adapter: IngestAdapter) -> None:
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS admission_events_unified ("
        "encounter_id TEXT PRIMARY KEY, "
        "patient_key TEXT NOT NULL, "
        "encounter_type TEXT NOT NULL, "
        "status TEXT NOT NULL, "
        "admit_ts TEXT, "
        "discharge_ts TEXT, "
        "los_hours REAL, "
        "facility_canonical_id TEXT, "
        "facility_name TEXT, "
        "is_acute BOOLEAN, "
        "source_event_ids TEXT, "
        "source_systems TEXT, "
        "has_adt BOOLEAN, "
        "has_claims BOOLEAN, "
        "has_auth BOOLEAN, "
        "confidence_score REAL, "
        "confidence_flags TEXT, "
        "admit_source_priority TEXT, "
        "discharge_source_priority TEXT, "
        "payer_id TEXT, "
        "drg TEXT, "
        "principal_diagnosis TEXT, "
        "admitting_diagnosis TEXT, "
        "diagnosis_codes TEXT, "
        "is_readmission BOOLEAN, "
        "readmission_days INTEGER, "
        "obs_to_ip_conversion BOOLEAN, "
        "transfer_chain TEXT, "
        "episode_id TEXT, "
        "created_at TEXT, "
        "updated_at TEXT, "
        "asre_version TEXT"
        ")"
    )


def _create_asre_encounters_detail(adapter: IngestAdapter) -> None:
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS asre_encounters_detail ("
        "encounter_id TEXT NOT NULL, "
        "event_id TEXT NOT NULL, "
        "event_type TEXT NOT NULL, "
        "event_ts TEXT, "
        "source_system TEXT, "
        "role_in_encounter TEXT, "
        "PRIMARY KEY (encounter_id, event_id)"
        ")"
    )


def _create_asre_audit_log(adapter: IngestAdapter) -> None:
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS asre_audit_log ("
        "log_id TEXT PRIMARY KEY, "
        "run_id TEXT NOT NULL, "
        "timestamp TEXT NOT NULL, "
        "action TEXT NOT NULL, "
        "entity_type TEXT NOT NULL, "
        "entity_id TEXT NOT NULL, "
        "detail TEXT"
        ")"
    )


def _create_asre_run_metrics(adapter: IngestAdapter) -> None:
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS asre_run_metrics ("
        "run_id TEXT NOT NULL, "
        "stage_name TEXT NOT NULL, "
        "started_at TEXT, "
        "completed_at TEXT, "
        "records_in INTEGER, "
        "records_out INTEGER, "
        "errors INTEGER, "
        "status TEXT, "
        "PRIMARY KEY (run_id, stage_name)"
        ")"
    )


def _create_asre_quality_metrics(adapter: IngestAdapter) -> None:
    adapter.execute_ddl(
        "CREATE TABLE IF NOT EXISTS asre_quality_metrics ("
        "run_id TEXT NOT NULL, "
        "metric_name TEXT NOT NULL, "
        "metric_value REAL, "
        "warn_threshold REAL, "
        "fail_threshold REAL, "
        "status TEXT, "
        "computed_at TEXT, "
        "PRIMARY KEY (run_id, metric_name)"
        ")"
    )
