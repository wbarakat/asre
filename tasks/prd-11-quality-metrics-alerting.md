# PRD-11: Quality Metrics and Alerting

## Introduction

Build the quality metrics computation and alerting system that evaluates pipeline output quality after each run. Metrics identify data quality issues; alerts notify operators when thresholds are breached. Also includes dbt schema tests for output table integrity.

**SPEC References:** §5.11 (quality check stage), §8.1 (dbt tests), §8.2 (custom quality metrics), §8.3 (alerting)

## Goals

- Compute all 11 quality metrics per run
- Evaluate metrics against configurable warn/fail thresholds
- Fire webhook alerts when thresholds are breached
- Run dbt schema tests for output table integrity
- Update watermark after successful quality check

## Dependencies

- PRD-10 (materialized output tables to compute metrics against)

## User Stories

### US-001: Implement quality metric computation
**Description:** As a developer, I need all quality metrics computed after each pipeline run.

**Acceptance Criteria:**
- [ ] `asre/quality/metrics.py` defines `QualityMetricComputer` class
- [ ] Computes all 11 metrics from SPEC §8.2:
  - `duplicate_rate`: duplicates found / total events ingested
  - `missing_discharge_rate`: open encounters > 48h / total encounters
  - `reconciliation_mismatch_rate`: encounters with TIMESTAMP_MISMATCH / encounters with multiple sources
  - `low_confidence_rate`: encounters with score < 0.60 / total encounters
  - `facility_unresolved_rate`: events with unresolved facility / total events
  - `auth_without_admit_rate`: auth signals with no encounter / total auth signals
  - `claims_only_rate`: claims-only encounters / total encounters
  - `avg_confidence_score`: mean confidence score across all encounters
  - `events_ingested`: count of events processed
  - `encounters_created`: new encounters in this run
  - `encounters_updated`: modified encounters in this run
  - `failed_event_rate`: failed events / total events ingested
- [ ] Each metric written to `asre_quality_metrics` table
- [ ] Unit test: known encounter set → correct metric values

### US-002: Implement threshold evaluation
**Description:** As a developer, I need each metric evaluated against warn and fail thresholds.

**Acceptance Criteria:**
- [ ] Each metric compared against `warn` and `fail` thresholds from config
- [ ] Status determined: `pass` (below warn), `warn` (between warn and fail), `fail` (above fail)
- [ ] Status stored on each metric row in `asre_quality_metrics`
- [ ] Thresholds per SPEC §4.2: duplicate_rate_warn=0.05, duplicate_rate_fail=0.15, etc.
- [ ] Unit test: metric 0.04 with warn=0.05 → pass
- [ ] Unit test: metric 0.08 with warn=0.05, fail=0.15 → warn
- [ ] Unit test: metric 0.20 with fail=0.15 → fail

### US-003: Implement webhook alerting
**Description:** As a developer, I need webhook alerts fired when metrics breach thresholds.

**Acceptance Criteria:**
- [ ] `asre/quality/alerter.py` defines `Alerter` class
- [ ] Fires HTTP POST to configured webhook URL(s) when any metric status is `warn` or `fail`
- [ ] Payload format per SPEC §8.3:
  ```json
  {
    "run_id": "...",
    "run_ts": "...",
    "alerts": [
      {"metric": "duplicate_rate", "value": 0.18, "threshold": 0.15, "severity": "fail"}
    ]
  }
  ```
- [ ] Payload contains ZERO PHI — only aggregate metrics
- [ ] Webhook failure (network error) is logged but does not block pipeline
- [ ] Multiple channels supported (list of webhook URLs)
- [ ] Unit test: mock webhook, verify payload structure
- [ ] Unit test: verify no PHI in payload

### US-004: Implement dbt schema tests
**Description:** As a developer, I need dbt tests to validate output table integrity.

**Acceptance Criteria:**
- [ ] dbt tests per SPEC §8.1:
  - `unique` on `admission_events_unified.encounter_id`
  - `not_null` on `admission_events_unified.patient_key`
  - `not_null` on `admission_events_unified.admit_ts`
  - `accepted_values` on `admission_events_unified.status` → [open, closed, cancelled]
  - `accepted_values` on `admission_events_unified.encounter_type` → [inpatient, observation, ed_only, outpatient]
  - `relationships` on `asre_encounters_detail.encounter_id` → `admission_events_unified.encounter_id`
- [ ] Tests defined in dbt YAML schema files
- [ ] `dbt test` passes on valid data
- [ ] `dbt test` fails on intentionally invalid data

### US-005: Implement QualityCheckStage
**Description:** As a developer, I need the quality check stage to plug into the pipeline.

**Acceptance Criteria:**
- [ ] `asre/quality/stage.py` defines `QualityCheckStage` implementing `PipelineStage`
- [ ] Computes metrics, evaluates thresholds, fires alerts if needed
- [ ] Updates watermark after successful completion
- [ ] Records stage metrics
- [ ] dbt model: `dbt_project/models/marts/asre_quality_metrics.sql`

## Functional Requirements

- FR-01: All metrics are computed from output tables (not intermediate state)
- FR-02: Webhook URL supports `${ENV_VAR}` substitution (secrets not in config)
- FR-03: Alert channels are configurable (list of webhooks)
- FR-04: Metrics with no denominator (e.g., zero encounters) → metric value = 0.0, status = pass
- FR-05: Watermark only updated after ALL quality checks pass (no failures above fail threshold)
- FR-06: `asre_quality_metrics` retains history (one row per metric per run, not overwritten)

## Non-Goals

- No Slack/PagerDuty native integrations (webhook only — customers route via their own integrations)
- No metric dashboards
- No custom metric definitions (fixed set of 11 metrics in v1)

## Technical Considerations

- Webhook dispatch should have a timeout (5 seconds) and retry (1 retry)
- Consider running dbt tests via subprocess call to `dbt test`
- Quality metrics table grows over time — consider retention policy in future
- Metrics should be computed from the materialized tables, not from in-memory data (ensures consistency)

## TDD Approach

1. Write tests for each metric computation with known data
2. Write tests for threshold evaluation (pass/warn/fail)
3. Write tests for webhook payload structure and PHI absence
4. Write dbt test YAML files
5. Write integration test: full pipeline → quality check → correct metrics
6. Implement to make tests pass

## Success Metrics

- All 11 metrics compute correctly against known test data
- Threshold evaluation produces correct status for each metric
- Webhook fires with correct payload (no PHI)
- dbt tests pass on valid output, fail on invalid output
- Watermark updated only after successful quality check
