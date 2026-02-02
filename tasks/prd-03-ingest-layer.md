# PRD-03: Ingest Layer

## Introduction

Build the ingest layer that reads source data from warehouse tables, applies filters, deduplicates on `source_record_id`, and manages watermarks for incremental processing. The development adapter targets PostgreSQL; warehouse-specific adapters (Snowflake, BigQuery, Redshift) are deferred to PRD-13.

**SPEC References:** §5.2 (ingest stage), §2.3 (runtime modes), §11.2 (event-level error tolerance), §11.3 (idempotency), §12.1-12.3 (schema migration)

## Goals

- Define IngestAdapter interface for warehouse abstraction
- Implement PostgreSQL adapter for development/testing
- Support both `full` and `incremental` run modes
- Ensure idempotent ingest via `source_record_id` dedup
- Implement per-source-type lookback buffers
- Establish schema migration infrastructure

## Dependencies

- PRD-01 (models, pipeline stage interface)
- PRD-02 (config for source definitions, schedule settings)

## User Stories

### US-001: Define IngestAdapter interface
**Description:** As a developer, I need an abstract adapter interface so warehouse implementations are swappable.

**Acceptance Criteria:**
- [ ] `asre/ingest/base.py` defines `IngestAdapter` ABC with methods:
  - `connect() -> None`
  - `disconnect() -> None`
  - `read_source(source_config, watermark, mode) -> list[dict]`
  - `get_watermark(source_name) -> datetime | None`
  - `set_watermark(source_name, timestamp) -> None`
  - `execute_ddl(sql: str) -> None` (for migrations)
  - `write_records(table: str, records: list[dict]) -> None` (for output)
- [ ] Unit test verifies interface is abstract (cannot instantiate directly)

### US-002: Implement PostgreSQL adapter
**Description:** As a developer, I need a Postgres adapter so I can develop and test locally.

**Acceptance Criteria:**
- [ ] `asre/ingest/postgres.py` implements `IngestAdapter` using SQLAlchemy + psycopg2
- [ ] `connect()` establishes connection using config credentials
- [ ] `read_source()` executes SELECT against configured table
- [ ] Handles connection errors gracefully with clear error messages
- [ ] Integration test: create test table in Postgres, read records back

### US-003: Implement full mode ingest
**Description:** As a developer, I need full mode to read all records from source tables.

**Acceptance Criteria:**
- [ ] When `mode=full`, `read_source` reads all records from the source table
- [ ] No watermark filtering applied in full mode
- [ ] `filters.exclude` rules are still applied
- [ ] Integration test: insert 100 records, full ingest returns all non-excluded records

### US-004: Implement incremental mode with lookback buffer
**Description:** As a developer, I need incremental mode to read only new/changed records with configurable lookback.

**Acceptance Criteria:**
- [ ] When `mode=incremental`, filter by `incremental_key > last_watermark - lookback_buffer`
- [ ] Lookback buffer resolved per source type: ADT uses `schedule.lookback_buffer.adt`, claims uses `schedule.lookback_buffer.claims`, etc.
- [ ] Falls back to `schedule.lookback_buffer.default` if source type not configured
- [ ] If no watermark exists (first run), behaves like full mode
- [ ] Integration test: insert records at various timestamps, verify only correct window returned

### US-005: Implement source_record_id dedup on ingest
**Description:** As a developer, I need ingest-time dedup so re-processing the same source data is idempotent.

**Acceptance Criteria:**
- [ ] Duplicate `source_record_id` values within the same batch are collapsed to one record
- [ ] The first occurrence (by source ordering) is kept
- [ ] Dedup count is tracked in stage metrics
- [ ] Integration test: insert records with duplicate source_record_ids, verify dedup

### US-006: Implement exclude filters
**Description:** As a developer, I need to apply exclude rules to skip irrelevant records during ingest.

**Acceptance Criteria:**
- [ ] `filters.exclude` expression from source config is applied as a WHERE NOT clause
- [ ] Supports SQL-like expressions (e.g., `hl7_event IN ('A08', 'A31')`)
- [ ] Records matching exclude filter are not returned
- [ ] Integration test: insert records with A01 and A08 events, verify A08 excluded

### US-007: Implement watermark management
**Description:** As a developer, I need watermark persistence so incremental runs know where to resume.

**Acceptance Criteria:**
- [ ] Watermarks stored in `asre_metadata` table (key-value)
- [ ] `get_watermark(source_name)` retrieves last watermark for a source
- [ ] `set_watermark(source_name, timestamp)` updates the watermark
- [ ] Watermarks are per-source (different sources have different watermarks)
- [ ] Integration test: set watermark, retrieve it, verify value

### US-008: Implement IngestStage
**Description:** As a developer, I need the ingest stage to plug into the pipeline runner.

**Acceptance Criteria:**
- [ ] `asre/ingest/stage.py` defines `IngestStage` implementing `PipelineStage`
- [ ] Iterates over all configured sources
- [ ] Returns raw records as list of dicts (not yet canonical events)
- [ ] Records stage metrics: records_in (from source), records_out (after dedup/filter), errors
- [ ] Preserves `_raw_payload` as the original source record dict

### US-009: Implement basic migration infrastructure
**Description:** As a developer, I need schema migration support so tables are created automatically.

**Acceptance Criteria:**
- [ ] `asre/migration/migrator.py` provides `Migrator` class
- [ ] Checks `asre_metadata` for `schema_version`; creates table if missing
- [ ] Discovers migration scripts in `asre/migration/versions/` ordered by filename prefix
- [ ] Runs pending migrations (version > current schema_version)
- [ ] `asre/migration/versions/001_initial_schema.py` creates `asre_metadata` and watermark tracking
- [ ] Integration test: run migrator on empty database, verify tables created

## Functional Requirements

- FR-01: Adapter must preserve all source columns in returned dicts (no column filtering at ingest)
- FR-02: `_raw_payload` is the complete source record serialized as JSON
- FR-03: Watermark key format: `watermark.<source_name>` in asre_metadata
- FR-04: Migration scripts implement `up(adapter)` and `down(adapter)` methods
- FR-05: Connection credentials come from `ASRE_WAREHOUSE_CREDENTIALS` env var or config
- FR-06: Adapter must handle empty source tables gracefully (return empty list, not error)

## Non-Goals

- No Snowflake/BigQuery/Redshift adapters (PRD-13)
- No canonicalization of ingested records (PRD-04)
- No writing to output tables (PRD-10)

## Technical Considerations

- Use SQLAlchemy Core (not ORM) for query building — keeps it lightweight
- Exclude filter expressions need safe evaluation (parameterized, no SQL injection)
- Watermark timestamps should be timezone-aware (UTC)
- Integration tests need a local PostgreSQL instance (use Docker or existing local Postgres)

## TDD Approach

1. Write adapter interface tests (verify ABC, method signatures)
2. Write integration tests for Postgres adapter (connect, read, write)
3. Write tests for watermark CRUD operations
4. Write tests for incremental filtering with lookback
5. Write tests for source_record_id dedup
6. Write tests for exclude filters
7. Write migration tests (fresh DB, upgrade path)
8. Implement to make tests pass

## Success Metrics

- Integration test: full ingest of 1000 test records completes
- Integration test: incremental ingest with lookback returns correct window
- Same data ingested twice produces identical results (idempotency verified)
