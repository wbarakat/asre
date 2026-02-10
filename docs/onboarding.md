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
