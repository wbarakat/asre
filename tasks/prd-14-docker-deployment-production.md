# PRD-14: Docker, Deployment, and Production Readiness

## Introduction

Package ASRE as a production-ready Docker container with auto-migration, dry-run mode, health checks, and CI/CD configuration. This is the final PRD that makes ASRE deployable to customer VPCs.

**SPEC References:** §12 (schema migration), §13.1 (container image), §13.2 (environment variables), §13.4 (orchestration integration), §13.5 (infrastructure requirements), §14 (security & compliance)

## Goals

- Build production Dockerfile with all dependencies
- Implement auto-migration on startup
- Support dry-run mode for validation
- Add container health check
- Configure CI/CD pipeline
- Document deployment

## Dependencies

- PRD-10 (full pipeline)
- PRD-13 (warehouse adapters)

## User Stories

### US-001: Create production Dockerfile
**Description:** As a DevOps engineer, I need a Docker image that packages ASRE for deployment.

**Acceptance Criteria:**
- [ ] `Dockerfile` based on Python 3.11 slim image
- [ ] Installs: ASRE package, dbt-core, all three warehouse adapters (dbt-snowflake, dbt-bigquery, dbt-redshift)
- [ ] Includes AHRQ CCS grouper data files
- [ ] Runs as non-root user (security requirement per SPEC §14.2)
- [ ] Entry point: `asre` CLI
- [ ] `docker build -t asre-engine:latest .` succeeds
- [ ] Image size < 500MB

### US-002: Implement auto-migration on startup
**Description:** As an operator, I need ASRE to automatically create/upgrade schema on startup.

**Acceptance Criteria:**
- [ ] On startup, before pipeline execution, check schema version in `asre_metadata`
- [ ] If `asre_metadata` doesn't exist → fresh install, run all migrations
- [ ] If schema_version behind → run pending migrations in order
- [ ] If schema_version current → skip migration
- [ ] Update `schema_version` in `asre_metadata` after successful migration
- [ ] Migration failure → clear error message, container exits with non-zero code
- [ ] Integration test: fresh DB → auto-migrate → verify tables exist

### US-003: Implement dry-run mode
**Description:** As an operator, I need to validate pipeline execution without writing to output tables.

**Acceptance Criteria:**
- [ ] `ASRE_DRY_RUN=true` or `asre run --dry-run` flag
- [ ] Pipeline runs all stages but skips materialization (no writes to output tables)
- [ ] Logs what would be written (encounter counts, metric values)
- [ ] Useful for validating new config before committing to writes
- [ ] Integration test: dry run produces logs but no table changes

### US-004: Add health check endpoint
**Description:** As a DevOps engineer, I need a health check for container orchestration.

**Acceptance Criteria:**
- [ ] Lightweight HTTP endpoint on configurable port (default 8080)
- [ ] `/health` returns 200 with `{"status": "ok"}` when container is running
- [ ] Returns 503 if pipeline is in a failed state
- [ ] HEALTHCHECK instruction in Dockerfile
- [ ] Minimal overhead (no web framework — use http.server or similar)

### US-005: Configure CI/CD pipeline
**Description:** As a developer, I need automated testing and building in CI.

**Acceptance Criteria:**
- [ ] GitHub Actions workflow (`.github/workflows/ci.yml`)
- [ ] Steps:
  1. Install dependencies
  2. Run unit tests (`pytest tests/unit/`)
  3. Run integration tests against Postgres (`pytest tests/integration/`)
  4. Run dbt compile + test
  5. Check snapshot diffs (fail on unapproved changes per SPEC §17.4)
  6. Build Docker image
- [ ] CI runs on push to main and all PRs
- [ ] CI blocks merge on test failures or unapproved snapshot changes

### US-006: Validate environment variable configuration
**Description:** As an operator, I need clear errors when required env vars are missing.

**Acceptance Criteria:**
- [ ] Required env vars per SPEC §13.2: ASRE_CUSTOMER_ID, ASRE_CONFIG_PATH, ASRE_WAREHOUSE_TYPE, ASRE_WAREHOUSE_CREDENTIALS
- [ ] Optional env vars: ASRE_RUN_MODE, ASRE_LOG_LEVEL, ASRE_ALERT_WEBHOOK_URL, ASRE_DRY_RUN
- [ ] Missing required env var → clear error message listing what's missing
- [ ] Validation runs before any pipeline work

### US-007: Document deployment process
**Description:** As an operator, I need documentation for deploying ASRE.

**Acceptance Criteria:**
- [ ] README.md with:
  - Quick start (local dev with Postgres)
  - Configuration guide (customer config structure)
  - Deployment guide (Docker, env vars, orchestration)
  - CLI reference (all commands)
  - Infrastructure requirements (CPU, memory, disk per SPEC §13.5)
  - Security notes (PHI handling, access control)

## Functional Requirements

- FR-01: Container runs with dedicated non-root service account
- FR-02: No PHI ever leaves the container (per SPEC §14.1)
- FR-03: TLS for all warehouse connections (per SPEC §14.3)
- FR-04: Config files support `${ENV_VAR}` for secrets (no plaintext credentials)
- FR-05: Docker image is compatible with AWS ECS and GCP Cloud Run
- FR-06: Orchestration integration examples for Airflow, dbt Cloud, cron (per SPEC §13.4)

## Non-Goals

- No Kubernetes Helm chart (customer manages their own orchestration)
- No built-in scheduler (ASRE is triggered externally)
- No multi-tenant support (single-tenant per SPEC §1.1)
- No web UI

## Technical Considerations

- Multi-stage Docker build to minimize image size
- Use `.dockerignore` to exclude test data, docs, and dev files
- Health check should be a separate lightweight process (not blocking the main pipeline)
- Consider using `CMD ["asre", "run"]` as default with override via command args
- CI Postgres service container for integration tests

## TDD Approach

1. Write test for env var validation (missing required vars)
2. Write test for auto-migration (fresh DB, upgrade)
3. Write test for dry-run mode (no writes)
4. Write Dockerfile and verify build
5. Write CI config and verify green pipeline

## Success Metrics

- `docker build` produces working image
- `docker run asre-engine asre run --mode full` succeeds against Postgres
- Auto-migration works on fresh and existing databases
- Dry-run mode completes without writing to output tables
- CI pipeline passes green
- Non-root user verified in container
