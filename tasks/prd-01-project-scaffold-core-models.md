# PRD-01: Project Scaffold and Core Models

## Introduction

Set up the ASRE project foundation: Python package structure, dependency management, core data models, structured logging, pipeline stage interface, dbt project scaffold, and test infrastructure. This PRD produces no pipeline behavior but establishes the contracts and tooling every subsequent PRD depends on.

**SPEC References:** §2.2 (tech stack), §2.4 (EventBatch), §3.2 (canonical event schema), §3.4 (output table schemas), §10.1 (structured logging), §10.2 (per-stage metrics), §16 (project structure), §17 (testing strategy)

## Goals

- Establish Python package with all dependencies declared
- Define core dataclasses matching SPEC schemas exactly
- Provide structured JSON logging with stage context
- Define pipeline stage interface (ABC) for consistent stage composition
- Scaffold dbt project targeting PostgreSQL for local development
- Set up pytest with golden-file (syrupy) support

## Dependencies

None — this is the foundation PRD.

## User Stories

### US-001: Create Python project structure
**Description:** As a developer, I need a properly configured Python project so I can install dependencies and run tests.

**Acceptance Criteria:**
- [ ] `pyproject.toml` declares Python 3.11+ requirement
- [ ] Dependencies include: pydantic, pyyaml, click, rapidfuzz, dbt-core, dbt-postgres, sqlalchemy, psycopg2-binary, pytest, pytest-syrupy
- [ ] `pip install -e .` succeeds
- [ ] Project follows structure from SPEC §16

### US-002: Define CanonicalEvent dataclass
**Description:** As a developer, I need the canonical event schema as a Python dataclass so all pipeline stages share a contract.

**Acceptance Criteria:**
- [ ] `asre/models/canonical_event.py` defines `CanonicalEvent` with all fields from SPEC §3.2
- [ ] Fields: event_id, patient_key, event_type, event_ts, source_system, source_record_id, facility_raw, facility_canonical_id, admit_flag, discharge_flag, auth_flag, patient_class, drg, principal_diagnosis, diagnosis_codes, auth_status, payer_id, ingested_at, batch_id, _raw_payload
- [ ] Proper types: str, bool, datetime, Optional where nullable in spec
- [ ] Dataclass is importable: `from asre.models.canonical_event import CanonicalEvent`
- [ ] Unit test verifies construction and field types

### US-003: Define Encounter dataclass
**Description:** As a developer, I need the encounter output schema as a Python dataclass matching `admission_events_unified`.

**Acceptance Criteria:**
- [ ] `asre/models/encounter.py` defines `Encounter` with all fields from SPEC §3.4 (`admission_events_unified`)
- [ ] Fields include: encounter_id, patient_key, encounter_type, status, admit_ts, discharge_ts, facility_canonical_id, facility_name, is_acute, los_hours, source_event_ids, source_systems, has_adt, has_claims, has_auth, confidence_score, confidence_flags, admit_source_priority, discharge_source_priority, payer_id, drg, principal_diagnosis, admitting_diagnosis, diagnosis_codes, is_readmission, readmission_days, obs_to_ip_conversion, transfer_chain, episode_id, created_at, updated_at, asre_version
- [ ] Unit test verifies construction

### US-004: Define Episode dataclass
**Description:** As a developer, I need the episode output schema as a Python dataclass matching `asre_episodes`.

**Acceptance Criteria:**
- [ ] `asre/models/episode.py` defines `Episode` with all fields from SPEC §3.4 (`asre_episodes`)
- [ ] Fields include: episode_id, patient_key, episode_type, episode_status, episode_start_ts, episode_end_ts, total_los_days, encounter_ids, encounter_count, facility_count, facility_sequence, includes_readmission, includes_post_acute, is_acute, principal_diagnosis, diagnosis_codes, confidence_score, created_at, updated_at
- [ ] Unit test verifies construction

### US-005: Define DiagnosisCode model
**Description:** As a developer, I need a structured model for diagnosis codes used across canonical events and encounters.

**Acceptance Criteria:**
- [ ] `asre/models/diagnosis.py` defines `DiagnosisCode` with fields: code, type, sequence, poa
- [ ] Can be serialized to/from dict (for JSON/VARIANT storage)
- [ ] Unit test verifies round-trip serialization

### US-006: Define EventBatch dataclass
**Description:** As a developer, I need the EventBatch abstraction for internal processing.

**Acceptance Criteria:**
- [ ] `asre/models/batch.py` defines `EventBatch` with `batch_id: str` and `events: list[CanonicalEvent]` per SPEC §2.4
- [ ] Unit test verifies construction and event access

### US-007: Implement structured JSON logging
**Description:** As a developer, I need structured logging so every pipeline stage emits consistent JSON logs with stage context.

**Acceptance Criteria:**
- [ ] `asre/observability/logger.py` provides a `get_logger(stage: str, run_id: str)` function
- [ ] Log output is JSON with fields: timestamp, level, stage, run_id, message (per SPEC §10.1)
- [ ] Additional fields (records_in, records_out, duration_seconds) can be passed as kwargs
- [ ] Unit test verifies JSON structure of emitted logs

### US-008: Implement per-stage metrics tracking
**Description:** As a developer, I need a metrics tracker so each pipeline stage records timing, throughput, and error counts.

**Acceptance Criteria:**
- [ ] `asre/observability/metrics.py` provides `StageMetrics` class
- [ ] Tracks: stage_name, started_at, completed_at, records_in, records_out, errors, status
- [ ] Context manager interface: `with StageMetrics("ingest", run_id) as m:` that auto-captures timing
- [ ] `to_dict()` method for persistence to `asre_run_metrics` table
- [ ] Unit test verifies timing capture and field population

### US-009: Define PipelineStage interface
**Description:** As a developer, I need a pipeline stage ABC so all stages have a consistent interface for composition.

**Acceptance Criteria:**
- [ ] `asre/pipeline/runner.py` defines `PipelineStage` ABC with `run(batch: EventBatch, context: PipelineContext) -> EventBatch` method
- [ ] `PipelineContext` holds: run_id, config, mode (full/incremental), metrics collector
- [ ] Unit test verifies a dummy stage implementation works

### US-010: Scaffold dbt project for PostgreSQL
**Description:** As a developer, I need a dbt project configured for local PostgreSQL development.

**Acceptance Criteria:**
- [ ] `dbt_project/dbt_project.yml` with project name `asre`
- [ ] `dbt_project/profiles.yml` targeting local PostgreSQL
- [ ] Directory structure: `models/staging/`, `models/intermediate/`, `models/marts/`
- [ ] `dbt debug` passes against local Postgres
- [ ] `.gitkeep` files in empty model directories

### US-011: Set up test infrastructure
**Description:** As a developer, I need pytest configured with golden-file support and test fixtures.

**Acceptance Criteria:**
- [ ] `tests/conftest.py` with shared fixtures (sample CanonicalEvent, sample Encounter, sample EventBatch)
- [ ] `tests/unit/` and `tests/integration/` directories exist
- [ ] pytest-syrupy configured for snapshot testing
- [ ] `pytest` runs successfully (even with zero test files initially)
- [ ] Makefile or script with common test commands

## Functional Requirements

- FR-01: Project uses `pyproject.toml` (PEP 621) for package metadata and dependencies
- FR-02: All dataclasses use Python `dataclasses` module (not Pydantic — Pydantic is for config validation only)
- FR-03: `CanonicalEvent.event_type` must accept only values from the normalized event type vocabulary (SPEC §3.3)
- FR-04: `Encounter.status` must accept only `open`, `closed`, `cancelled`
- FR-05: `Encounter.encounter_type` must accept only `inpatient`, `observation`, `ed_only`, `outpatient`
- FR-06: `Episode.episode_type` must accept only `surgical`, `medical`, `chronic_exacerbation`, `maternity`, `behavioral_health`, `unclassified`
- FR-07: `Episode.episode_status` must accept only `active`, `closed`, `reopened`
- FR-08: Structured logger must not emit any PII/PHI in log messages
- FR-09: All model `__init__` files must re-export key classes for clean imports

## Non-Goals

- No pipeline execution logic (just the interface)
- No config loading (PRD-02)
- No warehouse connectivity (PRD-03)
- No dbt models (just the scaffold)
- No CLI commands (PRD-02)

## Technical Considerations

- Use `dataclasses` with `__post_init__` for field validation where needed
- Use `datetime` for timestamps, `Optional[str]` for nullable strings
- `diagnosis_codes` field uses `list[DiagnosisCode]` in Python, stored as JSON/VARIANT in warehouse
- Logging uses Python's `logging` module with a custom JSON formatter
- dbt profiles.yml should use environment variables for Postgres connection

## TDD Approach

Write tests FIRST for each user story:
1. Test that each dataclass can be constructed with valid data
2. Test that invalid enum values raise errors
3. Test that EventBatch holds events correctly
4. Test that StageMetrics captures timing
5. Test that logger emits valid JSON
6. Then implement the code to make tests pass

## Success Metrics

- `pip install -e .` succeeds
- `pytest tests/unit/` passes with all model tests green
- `dbt debug` passes against local Postgres
- All imports work: `from asre.models import CanonicalEvent, Encounter, Episode, EventBatch`
