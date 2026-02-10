# ASRE Runbook

## Health check

- HTTP: `GET /health` on `ASRE_HEALTH_PORT` (default 8080)
- `200` = healthy, `503` = failed state

## Normal run

```
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode incremental
```

## Pre-production checklist

Run all checks before each release:

```
python3 -m mypy asre/ --strict
python3 -m pytest tests/unit/ -v --tb=short --cov=asre --cov-fail-under=80
python3 -m pytest tests/integration/ -v --tb=short
python3 -m pytest tests/unit/ --snapshot-warn-unused
```

For dbt validation:

```
cd dbt_project
dbt compile --target dev

# Ensure ASRE schema objects exist before dbt tests
python3 - <<'PY'
import os
from asre.ingest.postgres import PostgresAdapter
from asre.migration.migrator import Migrator

cfg = {
    "host": os.environ.get("ASRE_DB_HOST", "localhost"),
    "port": os.environ.get("ASRE_DB_PORT", "5432"),
    "database": os.environ.get("ASRE_DB_NAME", "asre_test"),
    "user": os.environ.get("ASRE_DB_USER", "asre_test"),
    "password": os.environ.get("ASRE_DB_PASSWORD", "asre_test"),
    "schema": "public",
}
adapter = PostgresAdapter(cfg)
adapter.connect()
try:
    Migrator(adapter).run()
finally:
    adapter.disconnect()
PY

dbt test --target dev
```

`dbt test` expects ASRE output tables to exist in the target schema.
If they are missing, run the pipeline once (or load fixtures) before dbt tests.

For connector-agnostic deployments, set `ASRE_WAREHOUSE_TYPE` and
`ASRE_WAREHOUSE_CREDENTIALS` via env (or provide equivalent values directly in
`config.yaml`). `asre run` validates config path + customer id first, then
resolves warehouse connection from config/env at runtime.

## Resume a failed run

```
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --resume <run_id>
```

Resume replays all stages from the start for correctness (intermediate
in-memory outputs are not persisted).

## Where to look when something fails

- `asre_checkpoints` — last completed stage + error
- `asre_run_metrics` — stage timing and counts
- `asre_quality_metrics` — quality summary and thresholds
- `asre_audit_log` — materialization events

## Migrations

Migrations run automatically before every pipeline execution. On a fresh install
all migrations are applied; on subsequent runs only pending migrations apply.

## Compatibility rules

- Run migrations whenever you upgrade the ASRE image or library version.
- Keep config files version-controlled alongside pipeline code; treat schema
  changes as backward-incompatible unless explicitly stated.

## Full refresh behavior

`--mode full` clears derived tables (`admission_events_unified`,
`asre_encounters_detail`, `asre_episodes`, `asre_quality_metrics`,
`asre_run_metrics`, `asre_audit_log`, `asre_canonical_events`) before rebuilding.

## Encoding requirement

PostgreSQL deployments must use UTF-8 server encoding. You can override the
check in dev via `ASRE_REQUIRE_UTF8=false` or `warehouse.connection.require_utf8: false`.

## Alerting

Set one or more webhook URLs in config:

```
alerting:
  webhook_urls:
    - "${ASRE_ALERT_WEBHOOK_URL}"
```

Thresholds are defined in `alerting.thresholds` (see `config.yaml`).
Quality gates can block a run when any metric hits a configured status via
`alerting.block_on_statuses` (default: `["fail"]`).

## Rollback strategy

ASRE writes idempotent, reproducible outputs. To rollback:

1. Revert your config/mappings to the last known good version.
2. Re-run a full backfill:

```
asre run --config-path "$ASRE_CONFIG_PATH" --customer-id "$ASRE_CUSTOMER_ID" --mode full
```

If you need a hard rollback, restore output tables from a warehouse snapshot and
then re-run incremental mode.
