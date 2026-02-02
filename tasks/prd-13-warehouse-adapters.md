# PRD-13: Warehouse Adapters (Snowflake, BigQuery, Redshift)

## Introduction

Extend the ingest layer with production warehouse adapters for Snowflake, BigQuery, and Redshift. This includes warehouse-specific SQL handling in dbt models and cross-warehouse compatibility for schema migrations.

**SPEC References:** §2.2 (tech stack — warehouse targets), §13.2 (environment variables), §13.3 (CLI test-connection)

## Goals

- Implement Snowflake, BigQuery, and Redshift ingest adapters
- Handle warehouse-specific SQL dialect differences in dbt models
- Ensure migrations work across all three warehouses
- Validate connectivity via `asre test-connection`

## Dependencies

- PRD-03 (IngestAdapter interface)
- PRD-10 (full pipeline working on PostgreSQL)

## User Stories

### US-001: Implement Snowflake adapter
**Description:** As a developer, I need a Snowflake adapter so ASRE runs in Snowflake customer environments.

**Acceptance Criteria:**
- [ ] `asre/ingest/snowflake.py` implements `IngestAdapter`
- [ ] Uses snowflake-connector-python
- [ ] Handles VARIANT type for JSON columns (_raw_payload, diagnosis_codes)
- [ ] Supports ARRAY type for list columns
- [ ] `test-connection` validates Snowflake connectivity
- [ ] All pipeline stages work end-to-end against Snowflake

### US-002: Implement BigQuery adapter
**Description:** As a developer, I need a BigQuery adapter for GCP customer environments.

**Acceptance Criteria:**
- [ ] `asre/ingest/bigquery.py` implements `IngestAdapter`
- [ ] Uses google-cloud-bigquery library
- [ ] Handles STRUCT/JSON types for complex columns
- [ ] Handles ARRAY type for list columns
- [ ] `test-connection` validates BigQuery connectivity
- [ ] All pipeline stages work end-to-end against BigQuery

### US-003: Implement Redshift adapter
**Description:** As a developer, I need a Redshift adapter for AWS customer environments.

**Acceptance Criteria:**
- [ ] `asre/ingest/redshift.py` implements `IngestAdapter`
- [ ] Uses redshift-connector library
- [ ] Handles SUPER type for JSON columns
- [ ] Handles VARCHAR(MAX) for large text fields
- [ ] `test-connection` validates Redshift connectivity
- [ ] All pipeline stages work end-to-end against Redshift

### US-004: Handle cross-warehouse dbt compatibility
**Description:** As a developer, I need dbt models that compile and run on all three warehouses.

**Acceptance Criteria:**
- [ ] dbt profiles for Snowflake, BigQuery, and Redshift
- [ ] Warehouse-specific SQL handled via dbt macros or Jinja conditionals:
  - VARIANT (Snowflake) vs JSON (BigQuery) vs SUPER (Redshift)
  - ARRAY syntax differences
  - Merge/upsert syntax differences
  - Timestamp function differences
- [ ] `dbt compile --target snowflake|bigquery|redshift` succeeds for all models
- [ ] `dbt test` passes on all three targets

### US-005: Handle cross-warehouse migrations
**Description:** As a developer, I need migration scripts that work on all three warehouses.

**Acceptance Criteria:**
- [ ] Migration scripts detect warehouse type from config
- [ ] DDL uses warehouse-appropriate syntax (CREATE TABLE, column types)
- [ ] Type mapping: VARIANT↔JSON↔SUPER, ARRAY↔ARRAY↔SUPER, TIMESTAMP_TZ↔TIMESTAMP↔TIMESTAMPTZ
- [ ] All existing migrations (001-004) work on all three warehouses

## Functional Requirements

- FR-01: Warehouse type configured via `ASRE_WAREHOUSE_TYPE` env var or config
- FR-02: Adapter selection is automatic based on warehouse type
- FR-03: Connection credentials via `ASRE_WAREHOUSE_CREDENTIALS` (connection string or file path)
- FR-04: Each adapter must handle connection pooling and retry for transient errors
- FR-05: PostgreSQL adapter remains available for development/testing

## Non-Goals

- No other warehouse targets (Databricks, etc.)
- No data lake support (S3, GCS, Azure Blob)
- No streaming/real-time adapters

## Technical Considerations

- Snowflake VARIANT requires `parse_json()` for inserts
- BigQuery uses `MERGE` syntax different from Snowflake/Redshift
- Redshift SUPER type has different query syntax than Snowflake VARIANT
- Consider testing against warehouse emulators or using integration test credentials
- dbt adapter packages: dbt-snowflake, dbt-bigquery, dbt-redshift

## TDD Approach

1. Write adapter interface compliance tests (run against each adapter)
2. Write connection/disconnect tests (mock for unit, real for integration)
3. Write read/write tests per adapter
4. Write dbt compilation tests for each target
5. Write migration tests per warehouse
6. Implement to make tests pass

## Success Metrics

- `asre test-connection` succeeds for each warehouse type
- Full pipeline runs end-to-end on each warehouse
- dbt models compile and test on all three targets
- Migrations execute correctly on all three warehouses
