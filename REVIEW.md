# ASRE Code Review Findings

Date: 2026-02-03
Scope: Review of current implementation against `SPEC.md` and `prd.json` with focus on runtime correctness and adherence to pipeline expectations.

---

## Finding 1 — [P1] Source config dict access
**File:** `asre/ingest/stage.py` (around line 63)

**Summary**
`IngestStage` assumes `source_cfg` is a dict (subscript access). However, `load_config()` returns `SourceConfig` Pydantic models, and `_create_pipeline_runner()` passes those models through. This will raise a runtime error (`TypeError: 'SourceConfig' object is not subscriptable`) during real runs.

**Evidence**
- `load_config()` returns `GlobalConfig` and sets `global_config.sources = sources` where `sources` is a list of `SourceConfig` models.
- `_create_pipeline_runner()` assigns `pipeline_config["sources"] = global_config.sources`.
- `IngestStage._ingest_source()` does `source_cfg["name"]`, `source_cfg["type"]`, `source_cfg["source"]`, etc.

**Impact**
Pipeline execution will fail at ingest with real configs, making the system non-functional outside of test fixtures that provide dicts.

**Suggested fix (not applied)**
Normalize configs to dicts once (e.g., `model_dump`) when building pipeline config, or update stages to accept Pydantic models via attribute access. Ensure consistent handling across all stages.

---

## Finding 2 — [P1] Source config dict access
**File:** `asre/canonicalize/stage.py` (around line 108)

**Summary**
`CanonicalizeStage` also subscripts `source_cfg` as a dict. This will fail for real `SourceConfig` models coming from `load_config()`.

**Evidence**
- `source_name = source_cfg["name"]`
- `source_type = source_cfg["type"]`
- `FieldMappings(**source_cfg["field_mappings"])`

**Impact**
Canonicalization will crash on first real run, even if ingest were fixed, because it assumes dicts instead of models.

**Suggested fix (not applied)**
Same as Finding 1: normalize config models to dicts before pipeline execution, or use Pydantic attributes consistently.

---

## Finding 3 — [P1] Checkpoint insert overwrites PK
**File:** `asre/pipeline/checkpoint.py` (around line 40)

**Summary**
`CheckpointManager.save_checkpoint()` writes a new row every stage but the table schema defines `run_id` as a PRIMARY KEY. The second stage will violate the PK constraint, preventing further checkpoints and breaking resume logic.

**Evidence**
- Table DDL: `run_id TEXT PRIMARY KEY`
- `save_checkpoint()` calls `write_records()` with a new row each stage (insert-only)

**Impact**
Pipeline runs will fail (or silently stop persisting checkpoints) on the second stage in environments enforcing PK constraints. Resume and status inspection will be incorrect.

**Suggested fix (not applied)**
Use an upsert (insert-or-update) keyed on `run_id`, or change the table schema to support multiple rows per run (e.g., composite key `run_id + stage_name`).

---

## Finding 4 — [P2] Completion stage metadata out of date
**File:** `asre/pipeline/checkpoint.py` (around line 58)

**Summary**
`mark_completed()` hardcodes `last_completed_stage = "quality_check"` and `stage_index = 8`, but the pipeline now includes 12 stages (episode stages added). Completion metadata is stale and misleading.

**Evidence**
- `_STAGE_ORDER` now includes `episode_stitch`, `episode_materialize`, `episode_quality`.
- `mark_completed()` still uses the pre-episode terminal stage.

**Impact**
Status and resume reporting is incorrect; operators may see runs as completed even when episode stages were not recorded.

**Suggested fix (not applied)**
Derive completion metadata from the actual stage list (e.g., last stage name and last index), or pass the final stage into `mark_completed()`.

---

## Finding 5 — [P2] Adapter selection ignores warehouse.type
**File:** `asre/cli/main.py` (around line 140)

**Summary**
CLI always creates a `PostgresAdapter` regardless of configured warehouse type. This breaks Snowflake/BigQuery/Redshift environments.

**Evidence**
- `_create_pipeline_runner()` uses `PostgresAdapter(global_config.warehouse.connection)` unconditionally.

**Impact**
Deployments targeting Snowflake, BigQuery, or Redshift will attempt to connect to Postgres and fail.

**Suggested fix (not applied)**
Introduce an adapter factory keyed on `warehouse.type` to instantiate the correct adapter implementation.

---

## Finding 6 — [P2] Pipeline config drops schedule/alerting/episode_stitching
**File:** `asre/cli/main.py` (around line 145)

**Summary**
Only a subset of `GlobalConfig` is passed to the pipeline. `schedule` (lookback buffers), `alerting` (thresholds/webhooks), and `episode_stitching` (linkage windows) are omitted.

**Evidence**
- `_create_pipeline_runner()` copies only `customer`, `sources`, `facility_aliases`, and some optional sections.
- `schedule`, `alerting`, `episode_stitching` are not included.

**Impact**
Defaults are used silently for lookback buffer, quality thresholds, and episode linkage windows even when config provides explicit values. This can materially change output behavior.

**Suggested fix (not applied)**
Include all relevant config sections when building the pipeline config or pass the entire `GlobalConfig` into the runner (with a documented interface).

---

## Finding 7 — [P2] Non-deterministic ingest ordering
**File:** `asre/ingest/query_builder.py` (around line 52)

**Summary**
Ingest queries omit `ORDER BY`, but dedup keeps the “first” record. Database ordering is undefined without an order clause, so dedup behavior is non-deterministic.

**Evidence**
- `build_query()` uses `SELECT * FROM {table}` with optional `WHERE`, no ordering.
- `dedup_by_source_record_id()` keeps first occurrence.

**Impact**
Idempotency can be broken: reprocessing identical inputs may yield different records kept or dropped depending on DB execution plan.

**Suggested fix (not applied)**
Add deterministic ordering, e.g. `ORDER BY incremental_key, source_record_id` or another stable key.

---

## Notes
- No code changes were made.
- Findings are ordered by severity (P1 highest).
- If you want a deeper pass or additional coverage (e.g., tests, dbt models, migrations), specify scope and I’ll extend this review.
