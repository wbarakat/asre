# ASRE - Admission Signal Reliability Engine

ASRE is a healthcare data reliability layer that ingests raw ADT, claims, authorization, and eligibility signals from your data warehouse and produces a single trusted output: **`admission_events_unified`** -- a stitched, deduplicated, reconciled encounter table with confidence scores.

ASRE is **not** an analytics engine, EHR replacement, or billing system. It reads pre-parsed warehouse tables and writes unified encounter data back to the same warehouse.

## Table of Contents

- [Quick Start](#quick-start)
- [Configuration Guide](#configuration-guide)
- [Deployment Guide](#deployment-guide)
- [CLI Reference](#cli-reference)
- [Infrastructure Requirements](#infrastructure-requirements)
- [Output Tables](#output-tables)
- [Architecture Overview](#architecture-overview)
- [Security Notes](#security-notes)
- [Testing](#testing)

---

## Quick Start

### Prerequisites

- Python 3.11+
- A supported warehouse: PostgreSQL, Snowflake, BigQuery, or Redshift
- Docker (for containerized deployment)

### Local Development Setup

```bash
# Clone and install
git clone <repo-url>
cd asre
pip install -e ".[dev]"

# Optional connector packages for non-Postgres local runs
# pip install -e ".[dev,snowflake]"
# pip install -e ".[dev,bigquery]"
# pip install -e ".[dev,redshift]"

# Set warehouse connection environment variables
cat > /tmp/asre_warehouse.json <<'JSON'
{
  "host": "localhost",
  "port": 5432,
  "database": "asre_dev",
  "user": "asre",
  "password": "asre_local",
  "schema": "public"
}
JSON

export ASRE_CONFIG_PATH="$PWD/customer_config"
export ASRE_CUSTOMER_ID="test_customer"
export ASRE_WAREHOUSE_TYPE="postgres"  # postgres | snowflake | bigquery | redshift
export ASRE_WAREHOUSE_CREDENTIALS="/tmp/asre_warehouse.json"

# Validate your configuration
asre validate-config \
  --config-path "$ASRE_CONFIG_PATH" \
  --customer-id "$ASRE_CUSTOMER_ID"

# Run the pipeline (incremental mode, the default)
asre run \
  --config-path "$ASRE_CONFIG_PATH" \
  --customer-id "$ASRE_CUSTOMER_ID" \
  --mode incremental

# Run tests
pytest tests/unit/ -v
pytest tests/integration/ -v

# Type checking
mypy asre/ --strict
```

### Using Make

```bash
make install          # pip install -e ".[dev]"
make test-unit        # Run unit tests
make test-integration # Run integration tests
make typecheck        # Run mypy
make check            # typecheck + all tests
make clean            # Remove caches
```

---

## Configuration Guide

ASRE uses YAML configuration files organized per customer. Secrets are injected via `${ENV_VAR}` substitution -- never store plaintext credentials in YAML files.

For the shortest setup, follow `docs/onboarding.md`. For operational guidance, see `docs/runbook.md`.

### Directory Structure

```
customer_config/<customer_id>/
  config.yaml              # Global pipeline configuration
  sources/
    adt_vendor_x.yaml      # Per-source: field mappings, event type rules, filters
    claims_clearinghouse.yaml
    auth_portal.yaml
  facility_aliases.yaml    # Canonical facilities with known name variants
```

### config.yaml

The global config file controls all pipeline behavior for a customer.

```yaml
customer:
  customer_id: acme_health
  customer_name: Acme Health System

warehouse:
  type: postgres                       # postgres | snowflake | bigquery | redshift
  connection: {}                       # populated from ASRE_WAREHOUSE_CREDENTIALS

schedule:
  mode: incremental                    # full | incremental
  lookback_buffer:
    default: "24h"
    adt: "24h"
    claims: "72h"
    auth: "24h"

encounter_stitching:
  time_window_hours: 48
  facility_must_match: true
  use_canonical_history: true         # preserve encounter_id for late data
  history_lookback_days: 90
  patient_class_transitions:
    - from: ed
      to: inpatient
      action: merge                    # merge | new_encounter
    - from: observation
      to: inpatient
      action: merge

deduplication:
  match_fields:
    - patient_key
    - event_type
    - facility_canonical_id
  time_tolerance_minutes: 30

reconciliation:
  timestamp_priority:                  # Higher = more trusted
    adt: 100
    claims: 80
    auth: 40
  classification_priority:
    claims: 100
    adt: 80
    auth: 40
  timestamp_tolerance_hours: 24

episode_stitching:
  readmission_window_days: 30
  post_acute_linkage_days: 14
  planned_return_days: 90
  ed_bounceback_days: 7

facility_normalization:
  fuzzy_threshold: 0.85               # Token sort ratio threshold for fuzzy matching
  abbreviations:
    MED CTR: MEDICAL CENTER
    HOSP: HOSPITAL

confidence_scoring:
  signal_weights:
    HAS_CLAIMS: 30
    HAS_ADT_ADMIT: 20
    HAS_ADT_DISCHARGE: 10
    HAS_AUTH: 10
    FACILITY_RESOLVED: 5
    TIMESTAMPS_CONSISTENT: 15
    PATIENT_CLASS_CONSISTENT: 10
  penalties:
    MISSING_DISCHARGE: -0.15
    ORPHAN_DISCHARGE: -0.20
    TIMESTAMP_MISMATCH: -0.10
    STALE_OPEN_ENCOUNTER: -0.20
  stale_encounter_thresholds:
    acute: 30
    ltach: 90
    snf: 120
    rehab: 60
    default: 30

alerting:
  webhook_urls:
    - "${ALERT_WEBHOOK_URL}"
  thresholds:
    duplicate_rate_warn: 0.05
    duplicate_rate_fail: 0.15
    missing_discharge_rate_warn: 0.10
    missing_discharge_rate_fail: 0.25
```

### Source Configuration (sources/*.yaml)

Each source (ADT feed, claims clearinghouse, auth portal) gets its own YAML file defining how to read and interpret the data.

```yaml
name: adt_vendor_x
type: adt                              # adt | claims | auth | eligibility

source:
  table: raw_adt_events
  incremental_key: message_ts          # Column used for watermark filtering

field_mappings:
  patient_key: patient_mrn
  event_ts: message_ts
  source_record_id: message_control_id
  facility_raw: sending_facility
  patient_class: patient_class
  npi: facility_npi

event_type_rules:
  source_field: hl7_event
  mappings:
    A01: ADMIT
    A02: TRANSFER_IN
    A03: DISCHARGE
    A04: REGISTRATION
    A06: OBS_TO_IP
    A11: CANCEL_ADMIT
    A13: CANCEL_DISCHARGE
  conditional_mappings:
    - when: "hl7_event == 'A01' AND patient_class == 'E'"
      event_type: ED_ARRIVAL
    - when: "hl7_event == 'A01' AND patient_class == 'O'"
      event_type: OBS_START
  admit_flag_expression: "event_type IN ('ADMIT', 'ED_ARRIVAL', 'OBS_START', 'TRANSFER_IN')"
  discharge_flag_expression: "event_type IN ('DISCHARGE', 'ED_DEPARTURE', 'OBS_END', 'TRANSFER_OUT')"

filters:
  exclude: "hl7_event IN ('A08', 'A31')"
```

### Facility Aliases (facility_aliases.yaml)

Maps known facility name variants to canonical IDs for facility normalization.

```yaml
facilities:
  - canonical_id: FAC_001
    canonical_name: St. Mary's Medical Center
    npi: "1234567890"
    ccn: "010001"
    facility_type: acute               # acute | snf | ltach | rehab | psych | ed_standalone
    aliases:
      - ST MARYS MEDICAL CTR
      - SAINT MARYS MEDICAL CENTER
```

---

## Deployment Guide

### Docker Build

```bash
docker build -t asre-engine:latest .
```

The Dockerfile uses a multi-stage build: a builder stage compiles wheels (including warehouse adapter packages for Snowflake, BigQuery, and Redshift), and the production image runs as a non-root `asre` user (UID 1000) for security.

### Environment Variables

All required environment variables must be set before running the container.

| Variable | Required | Description |
|----------|----------|-------------|
| `ASRE_CONFIG_PATH` | Yes | Path to customer config root directory |
| `ASRE_CUSTOMER_ID` | Yes | Customer subdirectory name |
| `ASRE_LICENSE_KEY` | Yes | RSA-256 signed JWT license key for pipeline execution |
| `ASRE_WAREHOUSE_TYPE` | Conditional | Required when `warehouse.type` is not fully defined in `config.yaml` |
| `ASRE_WAREHOUSE_CREDENTIALS` | Conditional | Required when `warehouse.connection` is not fully defined in `config.yaml` |
| `ASRE_RUN_MODE` | No | `full` or `incremental` (default: `incremental`) |
| `ASRE_LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARN`, `ERROR` (default: `INFO`) |
| `ASRE_ALERT_WEBHOOK_URL` | No | Webhook URL for quality alert notifications |
| `ASRE_DRY_RUN` | No | `true` to run without writing outputs |
| `ASRE_REQUIRE_UTF8` | No | `true` to enforce UTF-8 server/client encoding (default: `true`) |
| `ASRE_HEALTH_PORT` | No | Health check port (default: 8080) |
| `ASRE_HEALTH_BIND` | No | Health check bind address (default: 127.0.0.1) |

`ASRE_WAREHOUSE_CREDENTIALS` accepts:
- JSON string (connection dict)
- Path to JSON/YAML file (connection dict)
- Postgres/Redshift DSN string (e.g. `postgresql://user:pass@host:5432/db?schema=public`)

Most deployments set `ASRE_WAREHOUSE_TYPE` and `ASRE_WAREHOUSE_CREDENTIALS` via
environment variables (secrets manager) and keep `warehouse.connection: {}` in
customer config files.

PostgreSQL deployments should use UTF-8 server encoding. For local dev you can
disable enforcement via `ASRE_REQUIRE_UTF8=false` or
`warehouse.connection.require_utf8: false`.

### Running with Docker

```bash
# Validate configuration
docker run --rm \
  -e ASRE_CONFIG_PATH=/app/customer_config \
  -e ASRE_CUSTOMER_ID=acme_health \
  -e ASRE_WAREHOUSE_TYPE=postgres \
  -e ASRE_WAREHOUSE_CREDENTIALS=/app/warehouse.json \
  -v $(pwd)/warehouse.json:/app/warehouse.json \
  asre-engine:latest \
  validate-config --config-path /app/customer_config --customer-id acme_health

# Run pipeline (incremental)
docker run --rm \
  -e ASRE_CONFIG_PATH=/app/customer_config \
  -e ASRE_CUSTOMER_ID=acme_health \
  -e ASRE_WAREHOUSE_TYPE=postgres \
  -e ASRE_WAREHOUSE_CREDENTIALS=/app/warehouse.json \
  -v $(pwd)/warehouse.json:/app/warehouse.json \
  asre-engine:latest \
  run --config-path /app/customer_config --customer-id acme_health --mode incremental

# Full historical reprocessing
docker run --rm \
  -e ASRE_CONFIG_PATH=/app/customer_config \
  -e ASRE_CUSTOMER_ID=acme_health \
  -e ASRE_WAREHOUSE_TYPE=postgres \
  -e ASRE_WAREHOUSE_CREDENTIALS=/app/warehouse.json \
  -v $(pwd)/warehouse.json:/app/warehouse.json \
  # ... (same env vars) ...
  asre-engine:latest \
  run --config-path /app/customer_config --customer-id acme_health --mode full
```

### Orchestration

ASRE is designed as a scheduled batch container. It runs to completion, then exits. Common orchestration options:

- **AWS ECS Scheduled Task:** CloudWatch Events triggers an ECS Fargate task on a cron schedule.
- **Google Cloud Run Job:** Cloud Scheduler triggers a Cloud Run job.
- **Airflow:** Use `BashOperator` or `DockerOperator` calling `asre run`.
- **Cron:** `0 * * * * docker run asre-engine:latest asre run --config-path /app/customer_config --customer-id acme_health`
- **dbt Cloud:** Custom job step invoking the ASRE CLI.

### Health Check

The Docker image includes a health check on port 8080 (`/health` endpoint). For ECS or Cloud Run, configure the health check to poll this endpoint with a 30-second interval.

### Schema Migrations

ASRE automatically runs schema migrations before each pipeline execution. On a fresh install, all migrations are applied. On subsequent runs, only pending migrations run. Migration state is tracked in the `asre_metadata` table.

---

## CLI Reference

All commands accept `--config-path` (or `ASRE_CONFIG_PATH` env var) and `--customer-id` (or `ASRE_CUSTOMER_ID` env var).

### asre run

Run the ASRE pipeline.

```bash
asre run [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--mode` | `incremental` | `full` (clears derived tables and rebuilds) or `incremental` (since last watermark) |
| `--resume RUN_ID` | None | Replay a previously failed run by its run_id (replays all stages) |
| `--dry-run` | False | Run pipeline without writing to output tables |
| `--config-path` | (required) | Root config directory path |
| `--customer-id` | (required) | Customer subdirectory name |

### asre validate-config

Validate customer YAML configuration without running the pipeline.

```bash
asre validate-config --config-path PATH --customer-id ID
```

### asre test-connection

Test warehouse connectivity.

```bash
asre test-connection
```

### asre status

Show the last pipeline run status and summary metrics.

```bash
asre status --config-path PATH --customer-id ID
```

Output includes: run_id, status, last completed stage, timestamp, total records in/out/errors.

### asre inspect run

Show per-stage metrics for a specific pipeline run.

```bash
asre inspect run RUN_ID --config-path PATH --customer-id ID
```

### asre inspect encounter

Show encounter details with all source events.

```bash
asre inspect encounter ENCOUNTER_ID --config-path PATH --customer-id ID
```

### asre inspect errors

Show failed events from a pipeline run.

```bash
asre inspect errors --last-run --config-path PATH --customer-id ID
```

### asre facilities

Manage the facility registry.

```bash
# List unresolved facilities (flagged FACILITY_NEW_UNREVIEWED)
asre facilities --unresolved --config-path PATH --customer-id ID

# Map an unresolved facility to an existing canonical ID
asre facilities resolve FACILITY_ID --target TARGET_CANONICAL_ID \
  --config-path PATH --customer-id ID
```

### asre episodes

Manage episode computation.

```bash
# Recompute episodes from materialized encounters (without re-running full pipeline)
asre episodes --recompute --config-path PATH --customer-id ID
```

### asre validate-env

Validate that all required ASRE environment variables are set and valid.

```bash
asre validate-env
```

### asre migrate

Run or rollback database schema migrations.

```bash
# Run pending migrations
asre migrate --config-path PATH --customer-id ID

# Rollback to a specific version
asre migrate --rollback VERSION --config-path PATH --customer-id ID
```

### asre build-registry

Build the SQLite facility registry from NPPES and CMS POS sources.

```bash
asre build-registry --config-path PATH --customer-id ID
```

---

## Infrastructure Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 4 vCPU |
| Memory | 4 GB | 8 GB |
| Disk | 10 GB | 20 GB (for registry files, logs) |
| Network | Outbound to warehouse | Same VPC as warehouse |

### Supported Warehouses

- **PostgreSQL** -- used for local development and testing
- **Snowflake** -- production adapter (install with `pip install asre[snowflake]`)
- **Google BigQuery** -- production adapter (included in Docker image)
- **Amazon Redshift** -- production adapter (included in Docker image)

---

## Output Tables

ASRE materializes seven output tables in the configured warehouse schema:

| Table | Description |
|-------|-------------|
| `admission_events_unified` | Primary output. Encounter-level unified view with confidence scores. |
| `asre_encounters_detail` | Event-level detail with role classifications (admit_anchor, discharge_anchor, supporting, conflicting). |
| `asre_episodes` | Episode-level groupings linking related encounters (readmissions, transfers, post-acute chains). |
| `asre_facility_registry` | Canonical facility master with aliases, NPI, CCN, facility type. |
| `asre_quality_metrics` | Per-run quality metrics with pass/warn/fail status. |
| `asre_run_metrics` | Per-stage timing, record counts, and error counts for each pipeline run. |
| `asre_audit_log` | All pipeline modifications tracked for audit. |

---

## Architecture Overview

ASRE processes data through a sequential pipeline of 12 stages:

```
Ingest -> Canonicalize -> Facility Normalize -> Stitch -> Dedup -> Reconcile -> Score -> Materialize -> Quality Check -> Episode Stitch -> Episode Materialize -> Episode Quality
```

- **Ingest** -- Reads source tables from the warehouse using adapter-specific SQL, applies watermark filtering for incremental runs.
- **Canonicalize** -- Maps diverse source schemas to a single canonical event schema. Resolves HL7 event triggers and patient class into normalized event types (ADMIT, DISCHARGE, TRANSFER_IN, etc.).
- **Facility Normalize** -- Resolves facility name variants to canonical IDs via a matching cascade: exact match, NPI/CCN lookup, fuzzy match (token sort ratio), or create new with review flag.
- **Stitch** -- Groups canonical events into encounters by patient key, using configurable time windows and facility matching. Handles ED-to-IP merges, OBS-to-IP conversions, transfer chains, and cancellation events.
- **Dedup** -- Removes duplicate events within encounters using configurable match fields and time tolerance. Retains duplicates in the detail table for audit.
- **Reconcile** -- Resolves conflicts across ADT, claims, and auth sources. Selects timestamps by source priority and flags mismatches.
- **Score** -- Computes weighted confidence scores (0.0-1.0) using configurable signal weights and penalty flags.
- **Materialize** -- Writes unified encounters and detail records to output tables.
- **Quality Check** -- Computes per-run metrics, evaluates thresholds, and fires webhook alerts if thresholds are breached.
- **Episode Stitch** -- Groups related encounters into episodes using readmission windows, post-acute linkage, planned return windows, and ED bounceback rules.
- **Episode Materialize** -- Writes episode records to the `asre_episodes` output table.
- **Episode Quality** -- Computes episode-level quality metrics and evaluates thresholds.

---

## Security Notes

### PHI Handling

- All PHI stays within the customer's VPC. ASRE processes data in-place in the customer's warehouse.
- ASRE never transmits PHI externally. Alert webhooks contain only aggregate metrics (encounter counts, quality rates), never patient data.
- The Docker container runs as a non-root user (`asre`, UID 1000) to limit container escape risk.

### Credential Management

- All credentials use `${ENV_VAR}` substitution in YAML config files. Never store plaintext secrets in configuration.
- Set warehouse credentials and webhook URLs via environment variables or a secrets manager (AWS Secrets Manager, GCP Secret Manager, HashiCorp Vault).
- The Docker image does not embed any credentials.

### Access Control

- ASRE requires read access to source tables and read/write access to its output schema.
- Use a dedicated service account with minimal privileges scoped to the ASRE schema.
- For Snowflake: grant `USAGE` on warehouse, `SELECT` on source tables, and `CREATE TABLE` / `INSERT` / `UPDATE` on the ASRE schema.
- For BigQuery: grant `bigquery.dataViewer` on source datasets and `bigquery.dataEditor` on the ASRE dataset.
- For Redshift: grant `SELECT` on source schemas and full privileges on the ASRE schema.

### Network Security

- Deploy ASRE in the same VPC as the data warehouse to avoid data transit over public networks.
- Restrict outbound network access to the warehouse endpoint and (optionally) the alert webhook URL.
- No inbound ports are required for pipeline execution. Port 8080 is used only for container health checks within the orchestration platform.

---

## Testing

Tests use golden-file regression patterns. Changes to stitching, dedup, or reconciliation logic must not alter golden-file outputs without explicit approval.

```bash
pytest tests/unit/              # Unit tests
pytest tests/integration/       # Integration tests (requires Postgres)
pytest tests/unit/test_stitcher.py -k "test_name"  # Single test
mypy asre/ --strict             # Type checking
```

Unit test coverage targets: config loader, field mapper, event type resolver, facility normalizer, encounter stitcher, deduplicator, confidence scorer.

### Production Readiness Gate

Run this exact sequence before promoting to production:

```bash
# 1) Static checks
python3 -m mypy asre/ --strict

# 2) Unit tests (coverage gate)
python3 -m pytest tests/unit/ -v --tb=short --cov=asre --cov-report=term-missing --cov-fail-under=80

# 3) Integration tests (real Postgres)
ASRE_TEST_PG_HOST=localhost \
ASRE_TEST_PG_PORT=5432 \
ASRE_TEST_PG_DATABASE=asre_test \
ASRE_TEST_PG_USER=asre_test \
ASRE_TEST_PG_PASSWORD=asre_test \
ASRE_TEST_PG_SCHEMA=public \
python3 -m pytest tests/integration/ -v --tb=short

# 4) Snapshot consistency
python3 -m pytest tests/unit/ --snapshot-warn-unused

# 5) dbt validation
cd dbt_project
DBT_PROFILES_DIR=. \
ASRE_DB_HOST=localhost \
ASRE_DB_PORT=5432 \
ASRE_DB_USER=asre_test \
ASRE_DB_PASSWORD=asre_test \
ASRE_DB_NAME=asre_test \
dbt compile --target dev

ASRE_DB_HOST=localhost \
ASRE_DB_PORT=5432 \
ASRE_DB_USER=asre_test \
ASRE_DB_PASSWORD=asre_test \
ASRE_DB_NAME=asre_test \
python3 - <<'PY'
import os
from asre.ingest.postgres import PostgresAdapter
from asre.migration.migrator import Migrator

cfg = {
    "host": os.environ["ASRE_DB_HOST"],
    "port": os.environ["ASRE_DB_PORT"],
    "database": os.environ["ASRE_DB_NAME"],
    "user": os.environ["ASRE_DB_USER"],
    "password": os.environ["ASRE_DB_PASSWORD"],
    "schema": "public",
}
adapter = PostgresAdapter(cfg)
adapter.connect()
try:
    Migrator(adapter).run()
finally:
    adapter.disconnect()
PY

DBT_PROFILES_DIR=. \
ASRE_DB_HOST=localhost \
ASRE_DB_PORT=5432 \
ASRE_DB_USER=asre_test \
ASRE_DB_PASSWORD=asre_test \
ASRE_DB_NAME=asre_test \
dbt test --target dev
```

Notes:
- `dbt test` validates ASRE output tables and will fail if those relations do not exist yet.
- Run migrations (or one pipeline run) before `dbt test` so required ASRE tables exist.
- For release readiness, every step above must pass with no failures.
