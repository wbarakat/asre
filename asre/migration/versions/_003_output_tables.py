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
    from asre.migration.ddl_types import DDLTypeMapper

description = "output tables"


def upgrade(adapter: IngestAdapter) -> None:
    """Create all 5 ASRE output tables."""
    from asre.migration.ddl_types import DDLTypeMapper

    wt = getattr(adapter, "warehouse_type", "postgres")
    m = DDLTypeMapper(wt)

    _create_admission_events_unified(adapter, m)
    _create_asre_encounters_detail(adapter, m)
    _create_asre_audit_log(adapter, m)
    _create_asre_run_metrics(adapter, m)
    _create_asre_quality_metrics(adapter, m)


def _create_admission_events_unified(adapter: IngestAdapter, m: DDLTypeMapper) -> None:
    t = m.text()
    b = m.boolean()
    r = m.real()
    i = m.integer()
    pk = m.primary_key("encounter_id")

    cols = [
        pk,
        f"patient_key {t} NOT NULL",
        f"encounter_type {t} NOT NULL",
        f"status {t} NOT NULL",
        f"admit_ts {t}",
        f"discharge_ts {t}",
        f"los_hours {r}",
        f"facility_canonical_id {t}",
        f"facility_name {t}",
        f"is_acute {b}",
        f"source_event_ids {t}",
        f"source_systems {t}",
        f"has_adt {b}",
        f"has_claims {b}",
        f"has_auth {b}",
        f"confidence_score {r}",
        f"confidence_flags {t}",
        f"admit_source_priority {t}",
        f"discharge_source_priority {t}",
        f"payer_id {t}",
        f"drg {t}",
        f"principal_diagnosis {t}",
        f"admitting_diagnosis {t}",
        f"diagnosis_codes {t}",
        f"is_readmission {b}",
        f"readmission_days {i}",
        f"obs_to_ip_conversion {b}",
        f"transfer_chain {t}",
        f"episode_id {t}",
        f"created_at {t}",
        f"updated_at {t}",
        f"asre_version {t}",
    ]

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS admission_events_unified ({col_str})"
    )


def _create_asre_encounters_detail(adapter: IngestAdapter, m: DDLTypeMapper) -> None:
    t = m.text()
    cpk = m.composite_primary_key(["encounter_id", "event_id"])

    cols = [
        f"encounter_id {t} NOT NULL",
        f"event_id {t} NOT NULL",
        f"event_type {t} NOT NULL",
        f"event_ts {t}",
        f"source_system {t}",
        f"role_in_encounter {t}",
    ]
    if cpk:
        cols.append(cpk)

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_encounters_detail ({col_str})"
    )


def _create_asre_audit_log(adapter: IngestAdapter, m: DDLTypeMapper) -> None:
    t = m.text()
    pk = m.primary_key("log_id")

    cols = [
        pk,
        f"run_id {t} NOT NULL",
        f"timestamp {t} NOT NULL",
        f"action {t} NOT NULL",
        f"entity_type {t} NOT NULL",
        f"entity_id {t} NOT NULL",
        f"detail {t}",
    ]

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_audit_log ({col_str})"
    )


def _create_asre_run_metrics(adapter: IngestAdapter, m: DDLTypeMapper) -> None:
    t = m.text()
    i = m.integer()
    cpk = m.composite_primary_key(["run_id", "stage_name"])

    cols = [
        f"run_id {t} NOT NULL",
        f"stage_name {t} NOT NULL",
        f"started_at {t}",
        f"completed_at {t}",
        f"records_in {i}",
        f"records_out {i}",
        f"errors {i}",
        f"status {t}",
    ]
    if cpk:
        cols.append(cpk)

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_run_metrics ({col_str})"
    )


def _create_asre_quality_metrics(adapter: IngestAdapter, m: DDLTypeMapper) -> None:
    t = m.text()
    r = m.real()
    cpk = m.composite_primary_key(["run_id", "metric_name"])

    cols = [
        f"run_id {t} NOT NULL",
        f"metric_name {t} NOT NULL",
        f"metric_value {r}",
        f"warn_threshold {r}",
        f"fail_threshold {r}",
        f"status {t}",
        f"computed_at {t}",
    ]
    if cpk:
        cols.append(cpk)

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_quality_metrics ({col_str})"
    )
