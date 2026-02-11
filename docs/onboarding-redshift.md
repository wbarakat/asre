# Redshift Onboarding Guide

## Prerequisites

- ASRE container image or local install with Python 3.11+
- `redshift-connector` installed (`pip install redshift-connector`)
- An Amazon Redshift cluster or Redshift Serverless workgroup
- A database user with read access to source tables and write access to the ASRE schema
- Network connectivity from your ASRE host to the Redshift endpoint
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
  type: redshift
```

Leave the rest of `config.yaml` at defaults unless you need to tune stitching, scoring, or alerting.

## Step 2: Configure Credentials

You have two options for providing Redshift credentials.

### Option A: Credentials File (recommended)

Create a credentials file (e.g., `redshift-credentials.json`):

```json
{
  "host": "my-cluster.abc123.us-east-1.redshift.amazonaws.com",
  "port": 5439,
  "database": "analytics",
  "user": "asre_service",
  "password": "your-password-here",
  "schema": "asre",
  "ssl": true
}
```

### Option B: Connection String

```bash
export ASRE_WAREHOUSE_CREDENTIALS="redshift://asre_service:your-password@my-cluster.abc123.us-east-1.redshift.amazonaws.com:5439/analytics?schema=asre"
```

### Credential Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `host` | Yes | - | Redshift cluster endpoint |
| `port` | No | `5439` | Port number |
| `database` | Yes | - | Database name |
| `user` | Yes | - | Database username |
| `password` | Yes | - | Database password |
| `schema` | No | `public` | Target schema for ASRE output |
| `ssl` | No | `true` | Use SSL/TLS connection |

**Do not commit credentials to version control.**

## Step 3: Set Environment Variables

```bash
export ASRE_CONFIG_PATH="$PWD/customer_config"
export ASRE_CUSTOMER_ID="<your_customer_id>"
export ASRE_WAREHOUSE_TYPE="redshift"
export ASRE_WAREHOUSE_CREDENTIALS="/path/to/redshift-credentials.json"
export ASRE_LICENSE_KEY="eyJhbGc..."
```

## Step 4: Configure Source Mappings

Edit each file in `customer_config/<your_customer_id>/sources/` to match your Redshift tables.

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

## Redshift Permissions Checklist

The ASRE service user needs:

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

## Network Configuration

Redshift clusters run inside a VPC. Ensure your ASRE host can reach the cluster:

- **Same VPC:** No extra config needed.
- **Different VPC:** Set up VPC peering or use a Redshift publicly accessible endpoint.
- **On-premises / container:** Ensure the security group allows inbound on port 5439 from your ASRE host IP.

For Redshift Serverless, use the workgroup endpoint as the `host` value.

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `Connection refused` | Network/security group issue | Verify security group allows inbound on port 5439 from your host |
| `SSL connection error` | SSL configuration mismatch | Set `ssl: true` (default) or check cluster SSL settings |
| `Permission denied for schema` | Missing schema grants | Run the grants above for the ASRE user |
| `Disk full` | Cluster storage exhausted | Resize cluster or clean up old data, then re-run |
| `Connection timed out` | No network path to cluster | Check VPC routing, peering, or public accessibility settings |
