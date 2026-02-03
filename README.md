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
- PostgreSQL (local development warehouse stand-in)
- Docker (for containerized deployment)

### Local Development Setup

```bash
# Clone and install
git clone <repo-url>
cd asre
pip install -e ".[dev]"

# Set warehouse connection environment variables
export WAREHOUSE_HOST=localhost
export WAREHOUSE_PORT=5432
export WAREHOUSE_DATABASE=asre_dev
export WAREHOUSE_USER=asre
export WAREHOUSE_PASSWORD=asre_local
export WAREHOUSE_SCHEMA=public

# Validate your configuration
asre validate-config \
  --config-path customer_config \
  --customer-id test_customer

# Run the pipeline (incremental mode, the default)
asre run \
  --config-path customer_config \
  --customer-id test_customer \
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
  connection:
    host: "${WAREHOUSE_HOST}"
    port: "${WAREHOUSE_PORT}"
    database: "${WAREHOUSE_DATABASE}"
    user: "${WAREHOUSE_USER}"
    password: "${WAREHOUSE_PASSWORD}"
    schema: "${WAREHOUSE_SCHEMA}"

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
| `WAREHOUSE_HOST` | Yes | Database hostname |
| `WAREHOUSE_PORT` | Yes | Database port |
| `WAREHOUSE_DATABASE` | Yes | Database name |
| `WAREHOUSE_USER` | Yes | Database username |
| `WAREHOUSE_PASSWORD` | Yes | Database password |
| `WAREHOUSE_SCHEMA` | Yes | Target schema |
| `ASRE_CONFIG_PATH` | Yes | Path to customer config root directory |
| `ASRE_CUSTOMER_ID` | Yes | Customer subdirectory name |
| `ASRE_DRY_RUN` | No | Set to `1` to run without writing output |
| `ALERT_WEBHOOK_URL` | No | Webhook URL for quality alert notifications |

### Running with Docker

```bash
# Validate configuration
docker run --rm \
  -e WAREHOUSE_HOST=db.example.com \
  -e WAREHOUSE_PORT=5432 \
  -e WAREHOUSE_DATABASE=warehouse \
  -e WAREHOUSE_USER=asre_svc \
  -e WAREHOUSE_PASSWORD=secret \
  -e WAREHOUSE_SCHEMA=asre \
  asre-engine:latest \
  validate-config --config-path /app/customer_config --customer-id acme_health

# Run pipeline (incremental)
docker run --rm \
  -e WAREHOUSE_HOST=db.example.com \
  -e WAREHOUSE_PORT=5432 \
  -e WAREHOUSE_DATABASE=warehouse \
  -e WAREHOUSE_USER=asre_svc \
  -e WAREHOUSE_PASSWORD=secret \
  -e WAREHOUSE_SCHEMA=asre \
  asre-engine:latest \
  run --config-path /app/customer_config --customer-id acme_health --mode incremental

# Full historical reprocessing
docker run --rm \
  -e WAREHOUSE_HOST=db.example.com \
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
| `--mode` | `incremental` | `full` (reprocess all history) or `incremental` (since last watermark) |
| `--resume RUN_ID` | None | Resume a previously failed run by its run_id |
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

ASRE materializes five output tables in the configured warehouse schema:

| Table | Description |
|-------|-------------|
| `admission_events_unified` | Primary output. Encounter-level unified view with confidence scores. |
| `asre_encounters_detail` | Event-level detail with role classifications (admit_anchor, discharge_anchor, supporting, conflicting). |
| `asre_facility_registry` | Canonical facility master with aliases, NPI, CCN, facility type. |
| `asre_quality_metrics` | Per-run quality metrics with pass/warn/fail status. |
| `asre_audit_log` | All pipeline modifications tracked for audit. |

---

## Architecture Overview

ASRE processes data through a sequential pipeline of stages:

```
Ingest -> Canonicalize -> Facility Normalize -> Stitch -> Dedup -> Reconcile -> Score -> Materialize -> Quality Check
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
