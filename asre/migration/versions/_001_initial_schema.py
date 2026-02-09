"""001: Initial schema -- creates all 9 ASRE tables for v1.0.0 launch.

Tables created:
- asre_metadata: Key-value storage for schema version and watermarks
- admission_events_unified: Primary encounter-level unified view
- asre_encounters_detail: Event-level detail with role classifications
- asre_audit_log: All pipeline modifications for audit
- asre_run_metrics: Per-stage timing and throughput metrics
- asre_quality_metrics: Per-run quality metrics with pass/warn/fail status
- asre_episodes: Episode-level groupings of encounters
- asre_canonical_events: Canonical event history for lookback
- asre_facility_registry: Canonical facility master with aliases
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asre.ingest.base import IngestAdapter
    from asre.migration.ddl_types import DDLTypeMapper

description = "initial schema"


def upgrade(adapter: IngestAdapter) -> None:
    """Create all 9 ASRE tables."""
    from asre.migration.ddl_types import DDLTypeMapper

    wt = getattr(adapter, "warehouse_type", "postgres")
    m = DDLTypeMapper(wt)

    _create_asre_metadata(adapter, m, wt)
    _create_admission_events_unified(adapter, m)
    _create_asre_encounters_detail(adapter, m)
    _create_asre_audit_log(adapter, m)
    _create_asre_run_metrics(adapter, m)
    _create_asre_quality_metrics(adapter, m)
    _create_asre_episodes(adapter, m)
    _create_asre_canonical_events(adapter, m)
    _create_asre_facility_registry(adapter, m)


def _create_asre_metadata(
    adapter: IngestAdapter, m: DDLTypeMapper, wt: str
) -> None:
    cols = [
        f"key {m.text()} {'NOT NULL' if wt == 'bigquery' else ''}",
        f"value {m.text()} NOT NULL",
    ]

    # For non-bigquery, use PRIMARY KEY constraint on the key column directly
    if wt != "bigquery":
        cols[0] = f"key {m.text()} PRIMARY KEY"
    else:
        cols[0] = f"key {m.text()} NOT NULL"

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_metadata ({col_str})"
    )


def _create_admission_events_unified(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
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


def _create_asre_encounters_detail(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
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


def _create_asre_audit_log(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
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


def _create_asre_run_metrics(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
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


def _create_asre_quality_metrics(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
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
        f"metric_id {t}",
        f"detail {t}",
        f"run_ts {t}",
    ]
    if cpk:
        cols.append(cpk)

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_quality_metrics ({col_str})"
    )


def _create_asre_episodes(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
    t = m.text()
    b = m.boolean()
    r = m.real()
    i = m.integer()
    pk = m.primary_key("episode_id")

    cols = [
        pk,
        f"patient_key {t} NOT NULL",
        f"episode_type {t} NOT NULL",
        f"episode_status {t} NOT NULL",
        f"episode_start_ts {t}",
        f"episode_end_ts {t}",
        f"total_los_days {r}",
        f"encounter_ids {t}",
        f"encounter_count {i}",
        f"facility_count {i}",
        f"facility_sequence {t}",
        f"includes_readmission {b}",
        f"includes_post_acute {b}",
        f"is_acute {b}",
        f"principal_diagnosis {t}",
        f"diagnosis_codes {t}",
        f"confidence_score {r}",
        f"created_at {t}",
        f"updated_at {t}",
    ]

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_episodes ({col_str})"
    )


def _create_asre_canonical_events(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
    t = m.text()
    b = m.boolean()
    j = m.json()
    ts = m.timestamp()
    pk = m.primary_key("event_id")

    cols = [
        pk,
        f"patient_key {t} NOT NULL",
        f"event_type {t} NOT NULL",
        f"event_ts {ts} NOT NULL",
        f"source_system {t} NOT NULL",
        f"source_record_id {t} NOT NULL",
        f"facility_raw {t}",
        f"facility_canonical_id {t}",
        f"facility_match_type {t}",
        f"npi {t}",
        f"ccn {t}",
        f"admit_flag {b}",
        f"discharge_flag {b}",
        f"auth_flag {b}",
        f"patient_class {t}",
        f"drg {t}",
        f"principal_diagnosis {t}",
        f"diagnosis_codes {j}",
        f"auth_status {t}",
        f"payer_id {t}",
        f"ingested_at {ts}",
        f"batch_id {t}",
        f"raw_payload {j}",
        f"admitting_diagnosis {t}",
    ]

    col_str = ", ".join(cols)
    adapter.execute_ddl(
        f"CREATE TABLE IF NOT EXISTS asre_canonical_events ({col_str})"
    )


def _create_asre_facility_registry(
    adapter: IngestAdapter, m: DDLTypeMapper
) -> None:
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


def downgrade(adapter: IngestAdapter) -> None:
    """Drop all 9 ASRE tables in reverse dependency order."""
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_facility_registry")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_canonical_events")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_episodes")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_quality_metrics")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_run_metrics")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_audit_log")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_encounters_detail")
    adapter.execute_ddl("DROP TABLE IF EXISTS admission_events_unified")
    adapter.execute_ddl("DROP TABLE IF EXISTS asre_metadata")
