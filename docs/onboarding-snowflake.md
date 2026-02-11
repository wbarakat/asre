# Snowflake Onboarding Guide

## Prerequisites

- ASRE container image or local install with Python 3.11+
- `snowflake-connector-python` installed (`pip install snowflake-connector-python`)
- Snowflake account with a warehouse, database, and schema provisioned for ASRE
- A Snowflake user with read access to source tables and write access to the ASRE schema
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
  type: snowflake
```

Leave the rest of `config.yaml` at defaults unless you need to tune stitching, scoring, or alerting.

## Step 2: Configure Credentials

Create a credentials file (e.g., `snowflake-credentials.json`):

```json
{
  "account": "xy12345.us-east-1",
  "user": "ASRE_SERVICE_USER",
  "password": "your-password-here",
  "database": "ANALYTICS",
  "schema": "ASRE",
  "warehouse": "COMPUTE_WH",
  "role": "ASRE_ROLE"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `account` | Yes | Snowflake account identifier (e.g., `xy12345.us-east-1`) |
| `user` | Yes | Snowflake username |
| `password` | Yes | Snowflake password |
| `database` | Yes | Target database |
| `schema` | Yes | Target schema (default: `public`) |
| `warehouse` | Yes | Compute warehouse name |
| `role` | No | Snowflake role to assume |

**Do not commit this file to version control.**

## Step 3: Set Environment Variables

```bash
export ASRE_CONFIG_PATH="$PWD/customer_config"
export ASRE_CUSTOMER_ID="<your_customer_id>"
export ASRE_WAREHOUSE_TYPE="snowflake"
export ASRE_WAREHOUSE_CREDENTIALS="/path/to/snowflake-credentials.json"
export ASRE_LICENSE_KEY="eyJhbGc..."
```

Alternatively, pass credentials inline as JSON:

```bash
export ASRE_WAREHOUSE_CREDENTIALS='{"account":"xy12345.us-east-1","user":"ASRE_SERVICE_USER","password":"...","database":"ANALYTICS","schema":"ASRE","warehouse":"COMPUTE_WH"}'
```

## Step 4: Configure Source Mappings

Edit each file in `customer_config/<your_customer_id>/sources/` to match your Snowflake tables.

### ADT Source (`sources/adt.yaml`)

```yaml
name: adt_vendor
type: adt

source:
  table: RAW.ADT_EVENTS
  incremental_key: MESSAGE_TS

field_mappings:
  patient_key: PATIENT_ID
  event_ts: MESSAGE_TS
  source_record_id: MESSAGE_CONTROL_ID
  facility_raw: SENDING_FACILITY
  patient_class: PATIENT_CLASS
  npi: FACILITY_NPI

event_type_rules:
  source_field: HL7_EVENT
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
  table: RAW.CLAIMS
  incremental_key: PROCESSED_DATE

field_mappings:
  patient_key: MEMBER_ID
  event_ts: ADMIT_DATE
  source_record_id: CLAIM_ID
  facility_raw: FACILITY_NAME
  patient_class: PATIENT_CLASS
  drg: DRG
  principal_diagnosis: PRINCIPAL_DIAGNOSIS

paired_events:
  admit:
    event_ts: ADMIT_DATE
    event_type: CLAIM_ADMIT
  discharge:
    event_ts: DISCHARGE_DATE
    event_type: CLAIM_DISCHARGE

event_type_rules:
  source_field: CLAIM_TYPE
  mappings:
    IP: CLAIM_ADMIT
```

### Auth Source (`sources/auth.yaml`)

```yaml
name: auth_portal
type: auth

source:
  table: RAW.AUTH
  incremental_key: REQUEST_TS

field_mappings:
  patient_key: MEMBER_ID
  event_ts: REQUEST_TS
  source_record_id: AUTH_ID
  facility_raw: FACILITY_NAME
  patient_class: PATIENT_CLASS

event_type_rules:
  source_field: AUTH_STATUS
  mappings:
    approved: AUTH_APPROVED
    denied: AUTH_DENIED
    pending: AUTH_REQUESTED

auth_status_map:
  source_field: AUTH_STATUS
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

## Snowflake Permissions Checklist

The ASRE service user needs:

```sql
-- Read access to source tables
GRANT USAGE ON DATABASE ANALYTICS TO ROLE ASRE_ROLE;
GRANT USAGE ON SCHEMA ANALYTICS.RAW TO ROLE ASRE_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA ANALYTICS.RAW TO ROLE ASRE_ROLE;

-- Write access to ASRE output schema
GRANT USAGE ON SCHEMA ANALYTICS.ASRE TO ROLE ASRE_ROLE;
GRANT CREATE TABLE ON SCHEMA ANALYTICS.ASRE TO ROLE ASRE_ROLE;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA ANALYTICS.ASRE TO ROLE ASRE_ROLE;

-- Warehouse usage
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE ASRE_ROLE;
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `Account not found` | Wrong account identifier | Use the full account locator (e.g., `xy12345.us-east-1`), not just the account name |
| `Warehouse suspended` | Warehouse is not running | Set `AUTO_RESUME = TRUE` on the warehouse, or start it manually |
| `Permission denied on table` | Missing grants | Run the grants above for the ASRE role |
| `VARIANT column returns string` | Older connector version | Upgrade `snowflake-connector-python` to 3.0+ |
