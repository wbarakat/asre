# PostgreSQL Onboarding Guide

## Prerequisites

- ASRE container image or local install with Python 3.11+
- `psycopg2` installed (`pip install psycopg2-binary` for dev, `psycopg2` for production)
- A PostgreSQL 13+ instance with UTF-8 encoding
- A database user with read access to source tables and write access to the ASRE schema
- Your ASRE license key

## Step 1: Create Your Config Directory

```bash
cp -R customer_config/template_minimal customer_config/<your_customer_id>
```

Edit `customer_config/<your_customer_id>/config.yaml` and update:

```yaml
customer:
  customer_id: <your_customer_id>
  customer_name: <Your Health System>

warehouse:
  type: postgres
  connection:
    require_utf8: true
```

Leave the rest of `config.yaml` at defaults unless you need to tune stitching, scoring, or alerting.

## Step 2: Configure Credentials

You have three options for providing PostgreSQL credentials.

### Option A: Credentials File (recommended)

Create a credentials file (e.g., `postgres-credentials.json`):

```json
{
  "host": "db.example.com",
  "port": 5432,
  "database": "analytics",
  "user": "asre_service",
  "password": "your-password-here",
  "schema": "asre",
  "require_utf8": true
}
```

### Option B: Connection String

```bash
export ASRE_WAREHOUSE_CREDENTIALS="postgresql://asre_service:your-password@db.example.com:5432/analytics?schema=asre"
```

### Option C: Inline JSON

```bash
export ASRE_WAREHOUSE_CREDENTIALS='{"host":"db.example.com","port":5432,"database":"analytics","user":"asre_service","password":"...","schema":"asre"}'
```

### Credential Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `host` | Yes | `localhost` | Database hostname or IP |
| `port` | No | `5432` | Port number |
| `database` | Yes | - | Database name |
| `user` | Yes | - | Database username |
| `password` | Yes | - | Database password |
| `schema` | No | `public` | Target schema for ASRE output |
| `require_utf8` | No | `true` | Enforce UTF-8 server encoding |

**Do not commit credentials to version control.**

## Step 3: Set Environment Variables

```bash
export ASRE_CONFIG_PATH="$PWD/customer_config"
export ASRE_CUSTOMER_ID="<your_customer_id>"
export ASRE_WAREHOUSE_TYPE="postgres"
export ASRE_WAREHOUSE_CREDENTIALS="/path/to/postgres-credentials.json"
export ASRE_LICENSE_KEY="eyJhbGc..."
```

## Step 4: Configure Source Mappings

Edit each file in `customer_config/<your_customer_id>/sources/` to match your PostgreSQL tables.

### ADT Source (`sources/adt.yaml`)

```yaml
name: adt_vendor
type: adt

source:
  table: raw.adt_events
  incremental_key: message_ts

field_mappings:
  patient_key: patient_id
  event_ts: message_ts
  source_record_id: message_control_id
  facility_raw: sending_facility
  patient_class: patient_class
  npi: facility_npi

event_type_rules:
  source_field: hl7_event
  mappings:
    A01: ADMIT
    A03: DISCHARGE
    A04: REGISTRATION
    A11: CANCEL_ADMIT
    A13: CANCEL_DISCHARGE
```

### Claims Source (`sources/claims.yaml`)

```yaml
name: claims_clearinghouse
type: claims

source:
  table: raw.claims
  incremental_key: processed_date

field_mappings:
  patient_key: member_id
  event_ts: admit_date
  source_record_id: claim_id
  facility_raw: facility_name
  patient_class: patient_class
  drg: drg
  principal_diagnosis: principal_diagnosis

paired_events:
  admit:
    event_ts: admit_date
    event_type: CLAIM_ADMIT
  discharge:
    event_ts: discharge_date
    event_type: CLAIM_DISCHARGE

event_type_rules:
  source_field: claim_type
  mappings:
    IP: CLAIM_ADMIT
```

### Auth Source (`sources/auth.yaml`)

```yaml
name: auth_portal
type: auth

source:
  table: raw.auth
  incremental_key: request_ts

field_mappings:
  patient_key: member_id
  event_ts: request_ts
  source_record_id: auth_id
  facility_raw: facility_name
  patient_class: patient_class

event_type_rules:
  source_field: auth_status
  mappings:
    approved: AUTH_APPROVED
    denied: AUTH_DENIED
    pending: AUTH_REQUESTED

auth_status_map:
  source_field: auth_status
  mappings:
    approved: approved
    denied: denied
    pending: pending
```

Only include sources you have. If you don't have auth data, delete `auth.yaml`.

## Step 5: (Optional) Add Facility Aliases

If you have known facility names, edit `facility_aliases.yaml`:

```yaml
facilities:
  - canonical_id: "facility_001"
    canonical_name: "General Hospital"
    npi: "1234567890"
    ccn: "010001"
    facility_type: "acute"
    aliases:
      - "GEN HOSP"
      - "GENERAL HOSPITAL MAIN CAMPUS"
```

Otherwise, leave it as:

```yaml
facilities: []
```

ASRE will automatically flag unresolved facilities for review.

## Step 6: Validate and Test

```bash
# Validate config files
asre validate-config --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID"

# Validate environment variables
asre validate-env

# Test warehouse connectivity
asre test-connection --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID"
```

All three commands should exit with code 0. Fix any errors before proceeding.

## Step 7: Run the Pipeline

```bash
# First run (incremental from beginning)
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode incremental

# Or full historical reprocessing
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode full
```

## PostgreSQL Setup Checklist

### UTF-8 Encoding

ASRE requires UTF-8 encoding by default. Verify your database:

```sql
SHOW server_encoding;  -- Should return 'UTF8'
SHOW client_encoding;  -- Should return 'UTF8'
```

If your database isn't UTF-8 and you can't change it, set `require_utf8: false` in credentials or:

```bash
export ASRE_REQUIRE_UTF8=false
```

### Schema and Permissions

```sql
-- Create the ASRE schema
CREATE SCHEMA IF NOT EXISTS asre AUTHORIZATION asre_service;

-- Read access to source schema
GRANT USAGE ON SCHEMA raw TO asre_service;
GRANT SELECT ON ALL TABLES IN SCHEMA raw TO asre_service;

-- Write access to ASRE output schema
GRANT USAGE ON SCHEMA asre TO asre_service;
GRANT CREATE ON SCHEMA asre TO asre_service;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA asre TO asre_service;

-- For future tables created in these schemas
ALTER DEFAULT PRIVILEGES IN SCHEMA raw
  GRANT SELECT ON TABLES TO asre_service;
ALTER DEFAULT PRIVILEGES IN SCHEMA asre
  GRANT INSERT, UPDATE, DELETE ON TABLES TO asre_service;
```

## Local Development with Docker

For local testing, you can use the included Docker Compose setup:

```bash
docker compose up -d postgres

export ASRE_WAREHOUSE_TYPE="postgres"
export ASRE_WAREHOUSE_CREDENTIALS='{"host":"localhost","port":5432,"database":"asre_test","user":"asre_test","password":"asre_test","schema":"public","require_utf8":false}'
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `UTF-8 encoding required` | Database not UTF-8 | Create database with `ENCODING 'UTF8'`, or set `require_utf8: false` |
| `Connection refused` | PostgreSQL not running or wrong host/port | Verify host, port, and that PostgreSQL is accepting connections |
| `Password authentication failed` | Wrong credentials | Double-check username and password |
| `Permission denied for schema` | Missing schema grants | Run the grants above for the ASRE user |
| `Relation does not exist` | Source table not found | Verify table names in source YAML files match actual schema.table names |
