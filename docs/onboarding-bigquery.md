# BigQuery Onboarding Guide

## Prerequisites

- ASRE container image or local install with Python 3.11+
- `google-cloud-bigquery` installed (`pip install google-cloud-bigquery`)
- A GCP project with BigQuery enabled
- A dataset provisioned for ASRE output
- A service account with read access to source tables and write access to the ASRE dataset
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
  type: bigquery
```

Leave the rest of `config.yaml` at defaults unless you need to tune stitching, scoring, or alerting.

## Step 2: Create a Service Account

In the GCP Console (or via `gcloud`):

```bash
# Create service account
gcloud iam service-accounts create asre-pipeline \
  --display-name="ASRE Pipeline"

# Grant BigQuery Data Editor on the ASRE dataset
gcloud projects add-iam-policy-binding <your-project> \
  --member="serviceAccount:asre-pipeline@<your-project>.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

# Grant BigQuery Job User (to run queries)
gcloud projects add-iam-policy-binding <your-project> \
  --member="serviceAccount:asre-pipeline@<your-project>.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Export key file
gcloud iam service-accounts keys create /path/to/service-account.json \
  --iam-account=asre-pipeline@<your-project>.iam.gserviceaccount.com
```

## Step 3: Configure Credentials

Create a credentials file (e.g., `bigquery-credentials.json`):

```json
{
  "project": "your-gcp-project-id",
  "dataset": "asre",
  "location": "US",
  "credentials_path": "/path/to/service-account.json"
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `project` | Yes | GCP project ID |
| `dataset` | Yes | BigQuery dataset for ASRE output |
| `location` | No | BigQuery location (default: `US`) |
| `credentials_path` | No | Path to service account JSON key file |

**Authentication options:**

1. **Service account file** (recommended for production): Set `credentials_path` to the key file.
2. **Application Default Credentials** (for development): Omit `credentials_path` and run `gcloud auth application-default login`.
3. **Workload Identity** (GKE/Cloud Run): Omit `credentials_path`. Credentials are injected by the runtime.

**Do not commit key files to version control.**

## Step 4: Set Environment Variables

```bash
export ASRE_CONFIG_PATH="$PWD/customer_config"
export ASRE_CUSTOMER_ID="<your_customer_id>"
export ASRE_WAREHOUSE_TYPE="bigquery"
export ASRE_WAREHOUSE_CREDENTIALS="/path/to/bigquery-credentials.json"
export ASRE_LICENSE_KEY="eyJhbGc..."
```

Alternatively, pass credentials inline as JSON:

```bash
export ASRE_WAREHOUSE_CREDENTIALS='{"project":"your-gcp-project-id","dataset":"asre","location":"US","credentials_path":"/path/to/service-account.json"}'
```

## Step 5: Configure Source Mappings

Edit each file in `customer_config/<your_customer_id>/sources/` to match your BigQuery tables. Use dataset-relative references (`dataset.table`). If your project ID contains hyphens, wrap the reference in backticks (`` `my-project.dataset.table` ``).

### ADT Source (`sources/adt.yaml`)

```yaml
name: adt_vendor
type: adt

source:
  table: raw_data.adt_events
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
  table: raw_data.claims
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
  table: raw_data.auth
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

## Step 6: (Optional) Add Facility Aliases

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

## Step 7: Validate and Test

```bash
# Validate config files
asre validate-config --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID"

# Validate environment variables
asre validate-env

# Test warehouse connectivity
asre test-connection --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID"
```

All three commands should exit with code 0. Fix any errors before proceeding.

## Step 8: Run the Pipeline

```bash
# First run (incremental from beginning)
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode incremental

# Or full historical reprocessing
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode full
```

## BigQuery Permissions Checklist

The service account needs:

| Role | Scope | Purpose |
|------|-------|---------|
| `roles/bigquery.dataViewer` | Source dataset(s) | Read source tables |
| `roles/bigquery.dataEditor` | ASRE output dataset | Create/write output tables |
| `roles/bigquery.jobUser` | Project | Run queries |

For dataset-level access (preferred over project-level):

```bash
# Read access to source dataset
bq add-iam-policy-binding --member="serviceAccount:asre-pipeline@<project>.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataViewer" <project>:<source_dataset>

# Write access to ASRE dataset
bq add-iam-policy-binding --member="serviceAccount:asre-pipeline@<project>.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor" <project>:asre
```

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `403 Access Denied` | Missing IAM roles | Verify the service account has `dataViewer`, `dataEditor`, and `jobUser` roles |
| `404 Not found: Dataset` | Wrong project or dataset name | Double-check `project` and `dataset` in credentials |
| `Could not load credentials` | Missing or invalid key file | Verify `credentials_path` points to a valid service account JSON key |
| `Query exceeded resource limits` | Large source tables | Use incremental mode with a smaller lookback buffer |
