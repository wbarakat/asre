# ASRE Onboarding (Minimal)

This is the shortest path to a working ASRE deployment. Start with the
`customer_config/template_minimal` template and fill in only what you need.

## 1) Copy the template

```
cp -R customer_config/template_minimal customer_config/<customer_id>
```

## 2) Set environment variables

Provide warehouse credentials via `ASRE_WAREHOUSE_CREDENTIALS` (JSON string,
file path, or Postgres/Redshift DSN).

```
export ASRE_CONFIG_PATH="$PWD/customer_config"
export ASRE_CUSTOMER_ID="<customer_id>"
export ASRE_WAREHOUSE_TYPE="postgres"   # postgres | snowflake | bigquery | redshift
export ASRE_WAREHOUSE_CREDENTIALS="/path/to/warehouse.json"
export ASRE_LICENSE_KEY="eyJhbGc..."    # Required for asre run
```

Example `warehouse.json`:

```
{
  "host": "localhost",
  "port": 5432,
  "database": "asre_dev",
  "user": "asre",
  "password": "asre_local",
  "schema": "public",
  "require_utf8": true
}
```

PostgreSQL should run with UTF-8 server encoding. For local dev, you can set
`require_utf8` to `false` or export `ASRE_REQUIRE_UTF8=false`.

## 3) Update source mappings

Edit the files in `customer_config/<customer_id>/sources/` to match your
warehouse tables and column names:

- `adt.yaml`
- `claims.yaml`
- `auth.yaml`

Only update fields you actually have. Unused mappings can be left as-is or
removed when optional.

### Facility Mapping (Optional)

If your warehouse already has canonical facility IDs, you can bypass ASRE's
facility normalization entirely by mapping `facility_canonical_id`:

```yaml
field_mappings:
  patient_key: "patient_mrn"
  event_ts: "message_ts"
  source_record_id: "message_control_id"
  facility_canonical_id: "your_facility_id_column"  # Optional: bypass ASRE normalization
  facility_name: "your_facility_name_column"          # Optional: human-readable name
```

When `facility_canonical_id` is mapped, ASRE will:
- Set `facility_match_type` to `"customer_provided"` on every event
- Skip the facility normalization cascade (exact, NPI, CCN, fuzzy matching)
- Use your facility ID as-is for stitching, dedup, and scoring
- Use `facility_name` (if provided) in materialized output

If you don't map `facility_canonical_id`, ASRE uses its normal normalization
cascade to resolve facility names.

## 4) (Optional) Add facility aliases

If you have known facility names or NPI/CCN mappings, populate
`facility_aliases.yaml`. Otherwise keep this valid empty shape:

```yaml
facilities: []
```

## 5) Validate and run

```
asre validate-config --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID"

asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode incremental
```
