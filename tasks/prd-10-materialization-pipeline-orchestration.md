# PRD-10: Materialization and Pipeline Orchestration

## Introduction

Build the full pipeline orchestrator that sequences all 9 core stages, checkpoints intermediate results, supports resume on failure, and materializes output to warehouse tables. This PRD produces the first end-to-end working pipeline. Also includes readmission detection, audit logging, and CLI diagnostic commands.

**SPEC References:** §5.1 (pipeline stages), §5.10 (materialize), §5.11 (quality check), §11.1 (checkpointing), §11.2 (error tolerance), §11.3 (idempotency), §3.4 (output table schemas), §13.3 (CLI)

## Goals

- Orchestrate all 9 stages in sequence with checkpointing
- Support `full` and `incremental` modes
- Support `--resume <run_id>` for failed runs
- Materialize output via merge/upsert on encounter_id
- Compute readmission flags
- Write audit log entries
- Provide CLI inspection commands

## Dependencies

- PRD-01 through PRD-09 (all core stages)

## User Stories

### US-001: Implement pipeline orchestrator
**Description:** As a developer, I need all stages run in sequence with proper context passing.

**Acceptance Criteria:**
- [ ] `asre/pipeline/runner.py` defines `PipelineRunner` class
- [ ] Sequences stages: Ingest → Canonicalize → Facility Normalize → Stitch → Dedup → Reconcile → Score → Materialize → Quality Check
- [ ] Each stage receives `PipelineContext` with: run_id, config, mode, adapter, metrics
- [ ] Run ID generated at start: `run_{timestamp}` format
- [ ] Stage results pass to next stage (EventBatch → encounters → encounters)
- [ ] Integration test: full pipeline run with synthetic data

### US-002: Implement stage checkpointing
**Description:** As a developer, I need intermediate results persisted so failed runs can resume.

**Acceptance Criteria:**
- [ ] Each stage commits intermediate results to staging tables before next stage begins
- [ ] Checkpoint state includes: run_id, last_completed_stage, intermediate data reference
- [ ] Checkpoint stored in `asre_metadata` table
- [ ] On resume: pipeline skips completed stages, loads intermediate results, continues from next stage
- [ ] Integration test: fail pipeline at stage 5, resume → stages 1-4 skipped

### US-003: Implement resume support
**Description:** As a developer, I need `asre run --resume <run_id>` to continue from a failed run.

**Acceptance Criteria:**
- [ ] `--resume` flag on `asre run` CLI command
- [ ] Loads checkpoint for given run_id
- [ ] Validates checkpoint exists and is resumable
- [ ] Resumes from last completed stage + 1
- [ ] Clear error if run_id not found or already completed
- [ ] Unit test: resume logic with mock checkpoints

### US-004: Implement encounter materialization
**Description:** As a developer, I need encounters written to `admission_events_unified` via merge/upsert.

**Acceptance Criteria:**
- [ ] Merge/upsert keyed on `encounter_id`
- [ ] New encounters: INSERT with `created_at` set
- [ ] Updated encounters: UPDATE with `updated_at` set
- [ ] All fields from SPEC §3.4 `admission_events_unified` populated
- [ ] `asre_version` set to current engine version
- [ ] Integration test: materialize encounters, verify table contents

### US-005: Implement encounters detail materialization
**Description:** As a developer, I need event-level detail written to `asre_encounters_detail`.

**Acceptance Criteria:**
- [ ] Each event in an encounter gets a row in `asre_encounters_detail`
- [ ] `role_in_encounter` set per event: admit_anchor, discharge_anchor, supporting, conflicting, duplicate
- [ ] Admit anchor: the event that provides admit_ts
- [ ] Discharge anchor: the event that provides discharge_ts
- [ ] Supporting: events that corroborate but don't anchor
- [ ] Duplicate: events marked as duplicates in dedup stage
- [ ] Integration test: verify detail rows match encounter events

### US-006: Implement readmission detection
**Description:** As a developer, I need readmissions flagged on encounters.

**Acceptance Criteria:**
- [ ] `is_readmission = true` when patient is admitted to any acute facility within 30 days of a prior discharge from an acute facility
- [ ] `readmission_days` = days between prior discharge_ts and current admit_ts
- [ ] `readmission_days` only populated when `is_readmission = true`
- [ ] Only acute facilities count (check `is_acute` / `facility_type`)
- [ ] First admission is never a readmission
- [ ] Unit test: acute discharge Jan 1, acute admit Jan 15 → is_readmission=true, readmission_days=14
- [ ] Unit test: acute discharge Jan 1, SNF admit Jan 5 → is_readmission=false (SNF not acute)
- [ ] Unit test: acute discharge Jan 1, acute admit Feb 15 → is_readmission=false (>30 days)

### US-007: Implement audit logging
**Description:** As a developer, I need all encounter modifications tracked in `asre_audit_log`.

**Acceptance Criteria:**
- [ ] Each encounter create/update generates an audit log entry
- [ ] `asre_audit_log` fields: log_id, run_id, timestamp, action, entity_type, entity_id, detail
- [ ] Actions: `ingest`, `stitch`, `dedup`, `reconcile`, `score`, `normalize`, `materialize`
- [ ] Detail includes what changed (for updates: old value → new value)
- [ ] Integration test: verify audit log entries after pipeline run

### US-008: Write run metrics
**Description:** As a developer, I need per-stage timing and throughput written to `asre_run_metrics`.

**Acceptance Criteria:**
- [ ] After each stage, write a row to `asre_run_metrics`
- [ ] Fields: run_id, stage_name, started_at, completed_at, records_in, records_out, errors, status
- [ ] All 9 stages produce metrics rows
- [ ] Integration test: verify run_metrics table has 9 rows after full pipeline run

### US-009: Implement error tolerance
**Description:** As a developer, I need the pipeline to tolerate individual event failures up to a threshold.

**Acceptance Criteria:**
- [ ] Failed events are logged and excluded from downstream processing
- [ ] `failed_event_rate` computed: failed_events / total_events
- [ ] If `failed_event_rate > failed_event_rate_fail` threshold (from config), pipeline halts
- [ ] Below threshold: pipeline continues, failures tracked in metrics
- [ ] Unit test: 2% failure rate with 5% threshold → pipeline continues
- [ ] Unit test: 10% failure rate with 5% threshold → pipeline halts

### US-010: Implement CLI diagnostic commands
**Description:** As a developer, I need CLI commands to inspect pipeline results.

**Acceptance Criteria:**
- [ ] `asre run --mode full` runs full pipeline
- [ ] `asre run --mode incremental` runs incremental pipeline
- [ ] `asre status` shows last run status and summary
- [ ] `asre inspect run <run_id>` shows per-stage metrics for a run
- [ ] `asre inspect encounter <id>` shows encounter with all source events
- [ ] `asre inspect errors --last-run` shows failed events from last run

### US-011: Create dbt mart models
**Description:** As a developer, I need dbt models that materialize the output tables.

**Acceptance Criteria:**
- [ ] `dbt_project/models/marts/admission_events_unified.sql` — incremental model with merge on encounter_id
- [ ] `dbt_project/models/marts/asre_encounters_detail.sql`
- [ ] `dbt_project/models/marts/asre_audit_log.sql`
- [ ] `dbt_project/models/marts/asre_run_metrics.sql`
- [ ] Models compile and run against Postgres
- [ ] `dbt run` succeeds after pipeline populates staging tables

### US-012: Create output table migrations
**Description:** As a developer, I need migration scripts to create all output tables.

**Acceptance Criteria:**
- [ ] `asre/migration/versions/003_output_tables.py` creates:
  - admission_events_unified
  - asre_encounters_detail
  - asre_audit_log
  - asre_run_metrics
  - asre_quality_metrics
- [ ] Tables match SPEC §3.4 schemas exactly
- [ ] Migration is idempotent (re-running doesn't error)
- [ ] Integration test: run migration on empty DB, verify tables exist with correct columns

## Functional Requirements

- FR-01: Pipeline run is atomic per stage — either a stage completes fully or it doesn't modify outputs
- FR-02: Incremental mode uses merge/upsert — never drops and recreates tables
- FR-03: Encounter ID stability is verified: re-running with same data produces same encounter_ids
- FR-04: Audit log detail field is JSON containing relevant change information
- FR-05: Pipeline produces non-zero output when given valid input (sanity check)
- FR-06: `asre_version` follows semver format (e.g., "1.0.0")

## Non-Goals

- No episode processing (PRD-12)
- No quality metrics computation (PRD-11 — just call quality stage)
- No warehouse-specific adapters (PRD-13)
- No Docker packaging (PRD-14)

## Technical Considerations

- Checkpointing can use staging tables or temporary tables depending on warehouse
- For Postgres dev: use UPSERT (INSERT ON CONFLICT) for merge semantics
- Run metrics should be written even if a stage fails (record the failure)
- Consider a `--dry-run` mode that runs pipeline without writing outputs (SPEC §13.2)

## TDD Approach

1. Write integration test for full pipeline with synthetic data (end-to-end)
2. Write test for checkpoint/resume behavior
3. Write test for readmission detection logic
4. Write test for error tolerance thresholds
5. Write test for audit log entries
6. Write test for idempotent re-processing
7. Implement to make tests pass

## Success Metrics

- `asre run --mode full` with synthetic data produces populated output tables
- Same data processed twice produces identical outputs (idempotency)
- Failed pipeline resumes correctly from checkpoint
- All output tables match SPEC schemas
- End-to-end integration test with ADT + claims + auth data passes
