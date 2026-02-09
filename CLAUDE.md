# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ASRE (Admission Signal Reliability Engine) is a healthcare data reliability layer that ingests raw ADT, claims, authorization, and eligibility signals and produces a single trusted output: `admission_events_unified` -- a stitched, deduplicated, reconciled encounter table. It is NOT an analytics engine, EHR replacement, or billing system.

## Tech Stack

- **Language:** Python 3.11+
- **Transformation:** dbt-core with warehouse-specific adapters (Snowflake, BigQuery, Redshift)
- **Config validation:** Pydantic
- **Facility matching:** rapidfuzz
- **Container:** Docker (ECS / Cloud Run compatible)
- **Config format:** YAML with `${ENV_VAR}` substitution for secrets

## Build & Run Commands

```bash
# CLI commands (inside container or local dev)
asre run --mode full              # Full historical reprocessing
asre run --mode incremental       # Process since last watermark (default)
asre validate-config              # Validate YAML config only
asre test-connection              # Test warehouse connectivity
asre status                       # Show pipeline status

# dbt (from dbt_project/ directory)
dbt run                           # Execute all models
dbt test                          # Run schema + data tests
```

## Testing

Tests use golden-file regression patterns. Changes to stitching, dedup, or reconciliation must not alter golden-file outputs without explicit approval.

```bash
pytest                            # Run all tests
pytest tests/unit/                # Unit tests only
pytest tests/integration/         # Integration tests (uses Postgres as warehouse stand-in)
pytest tests/unit/test_stitcher.py -k "test_name"  # Single test
```

Unit test coverage targets: config loader, field mapper, event type resolver, facility normalizer, encounter stitcher, deduplicator, confidence scorer.

## Architecture

### Pipeline Stages (sequential, in order)

```
Ingest -> Canonicalize -> Facility Normalize -> Stitch -> Dedup -> Reconcile -> Score -> Materialize -> Quality Check
```

All internal processing uses the `EventBatch` abstraction (streaming-ready interface, batch-only in v1). The pipeline runner in `pipeline/runner.py` orchestrates stage sequencing.

### Key Module Responsibilities

- **`ingest/`** -- Warehouse adapter interface (`base.py`) with Snowflake/BigQuery/Redshift implementations. Reads source tables, applies watermark filtering and exclusion rules.
- **`canonicalize/`** -- Maps diverse source schemas to the single `asre_canonical_events` schema. `event_type_resolver.py` converts HL7 triggers + patient class into normalized event types (ADMIT, DISCHARGE, TRANSFER_IN, etc.).
- **`facility/`** -- String normalization pipeline (uppercase, strip punctuation, expand abbreviations, fuzzy match). Matching cascade: exact -> NPI/CCN lookup -> fuzzy (token sort ratio >= threshold) -> create new + flag for review.
- **`stitch/`** -- Groups canonical events into encounters by patient_key, sorted by event_ts. Uses configurable time windows, facility matching, and patient class transition rules. Handles ED->IP merges, OBS->IP conversions, transfer chains, and cancellation events.
- **`dedup/`** -- Removes duplicate events within encounters using match_fields + time_tolerance_minutes. Keeps highest source priority; retains duplicates in detail table for audit.
- **`reconcile/`** -- Resolves conflicts across ADT/claims/auth sources. Selects timestamps by source priority, resolves encounter type, flags mismatches (TIMESTAMP_MISMATCH, CLAIMS_ONLY_ENCOUNTER, ORPHAN_DISCHARGE, etc.).
- **`score/`** -- Weighted confidence scoring (0.0-1.0). Signals: HAS_CLAIMS(30), HAS_ADT_ADMIT(20), TIMESTAMPS_CONSISTENT(15), etc. Penalties for missing discharge, orphan discharge, stale encounters. All weights/penalties configurable per customer.
- **`quality/`** -- Computes per-run metrics (duplicate_rate, missing_discharge_rate, etc.), evaluates thresholds, fires webhook alerts.
- **`models/`** -- Core dataclasses: `CanonicalEvent`, `Encounter`, `EventBatch`.
- **`dbt_project/`** -- SQL models organized as staging -> intermediate -> marts. Marts produce the 5 output tables.

### Output Tables

1. **`admission_events_unified`** -- Primary output. Encounter-level unified view with confidence scores.
2. **`asre_encounters_detail`** -- Event-level detail with role classifications (admit_anchor, discharge_anchor, supporting, conflicting).
3. **`asre_facility_registry`** -- Canonical facility master with aliases, NPI, CCN, facility type.
4. **`asre_quality_metrics`** -- Per-run quality metrics with pass/warn/fail status.
5. **`asre_audit_log`** -- All pipeline modifications tracked for audit.

### Data Flow

All inputs (ADT, claims, auth, eligibility) are pre-parsed warehouse tables. ASRE reads from them, never from raw message streams. Each source gets a YAML mapping config that defines field mappings, event type rules, and filters. Claims sources can emit paired events (one source row -> admit + discharge canonical events).

### Config Structure

```
customer_config/<customer_id>/
  config.yaml                   # Global: schedule, stitching rules, dedup settings, scoring weights, alerting thresholds
  sources/
    adt_vendor_x.yaml           # Per-source: table ref, field mappings, event type rules, filters
    claims_clearinghouse.yaml
    auth_portal.yaml
  facility_aliases.yaml         # Canonical facilities with known name variants
```

Source priority for reconciliation is configured in `config.yaml` under `reconciliation.source_priority` (higher number = more trusted for timestamps).

## Key Domain Concepts

- **Encounter stitching** groups events into encounters using time windows and facility matching. Stale encounter thresholds vary by facility type (acute: 30d, LTACH: 90d, SNF: 120d, etc.).
- **Transfer chains** link encounters across facilities (discharge from A within time_window of admit at B). Each facility segment is its own encounter linked via `transfer_chain` array.
- **Confidence scoring** uses weighted signals + penalty flags. Score ranges: High (0.85-1.0), Medium (0.60-0.84), Low (0.30-0.59), Very Low (0.00-0.29).
- **Facility normalization** resolves variant names to canonical IDs. Unresolved facilities get flagged `FACILITY_NEW_UNREVIEWED` for human review.

## Security Constraints

- All PHI stays in customer's VPC. ASRE never transmits PHI externally.
- Alert webhooks contain only aggregate metrics, never PHI.
- No plaintext credentials in YAML -- use `${ENV_VAR}` substitution.

## Bug Reporting Protocol

When a bug is reported, do not start by trying to fix it. Instead:
1. Write a test that reproduces the bug
2. Have subagents try to fix the bug and prove the fix with a passing test

## Workflow Orchestration

### Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately -- don't keep patching
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### Self-Improvement Loop
- After ANY correction from the user, update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes -- don't overengineer
- Challenge your own work before presenting it

### Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests -- then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First:** Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan:** Check in before starting implementation
3. **Track Progress:** Mark items complete as you go
4. **Explain Changes:** High-level summary at each step
5. **Document Results:** Add review section to `tasks/todo.md`
6. **Capture Lessons:** Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **No Laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary. Avoid introducing bugs.
