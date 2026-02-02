# PRD-08: Cross-Source Reconciliation

## Introduction

Build the reconciliation stage that resolves conflicts across ADT, claims, and auth sources. When multiple sources contribute events to the same encounter, reconciliation determines which source provides timestamps, encounter type, DRG, diagnosis, and payer — and flags mismatches for downstream confidence scoring.

**SPEC References:** §5.8 (cross-source reconciliation), §4.2 (reconciliation config)

## Goals

- Select encounter timestamps from highest-priority source
- Resolve encounter type, DRG, payer, and diagnoses from highest-priority source
- Apply auth signals as validation-only (never anchoring)
- Generate conflict/quality flags for downstream scoring

## Dependencies

- PRD-01 (models)
- PRD-02 (ReconciliationConfig with priority settings)
- PRD-07 (deduplicated encounters)

## User Stories

### US-001: Implement timestamp selection by source priority
**Description:** As a developer, I need encounter timestamps selected from the most trusted source.

**Acceptance Criteria:**
- [ ] `asre/reconcile/reconciler.py` defines `Reconciler` class
- [ ] `admit_ts` is set from the source with highest `timestamp_priority` (default: ADT=100, claims=80, auth=40)
- [ ] `discharge_ts` is set from the source with highest `timestamp_priority`
- [ ] `admit_source_priority` records which source provided admit_ts (e.g., "adt")
- [ ] `discharge_source_priority` records which source provided discharge_ts
- [ ] Unit test: encounter with ADT admit at 10:00 and claims admit at 10:30 → admit_ts=10:00 (ADT), admit_source_priority="adt"

### US-002: Implement classification resolution by source priority
**Description:** As a developer, I need encounter type, DRG, payer, and diagnoses from the most trusted classification source.

**Acceptance Criteria:**
- [ ] `encounter_type` is set from the source with highest `classification_priority` (default: claims=100, ADT=80, auth=40)
- [ ] `drg` is set from claims when available
- [ ] `payer_id` is set from highest classification priority source
- [ ] `principal_diagnosis` is set from claims when available
- [ ] `admitting_diagnosis` is set from ADT when available
- [ ] `diagnosis_codes` aggregated from all sources with claims taking precedence
- [ ] Unit test: ADT says observation, claims says inpatient → encounter_type=inpatient (claims priority)

### US-003: Implement auth reconciliation rules
**Description:** As a developer, I need auth signals to validate encounters without anchoring them.

**Acceptance Criteria:**
- [ ] Auth events are never used as the anchor for encounter creation
- [ ] Auth has lowest priority for both timestamps and classification
- [ ] If auth exists with matching encounter: noted as supporting signal (used by confidence scorer)
- [ ] If auth exists with NO matching encounter: flag `AUTH_WITHOUT_ADMIT`
- [ ] Unit test: encounter with auth + ADT → auth doesn't override any fields
- [ ] Unit test: orphan auth signal → AUTH_WITHOUT_ADMIT flag

### US-004: Flag timestamp mismatches
**Description:** As a developer, I need mismatches between sources flagged for quality tracking.

**Acceptance Criteria:**
- [ ] `TIMESTAMP_MISMATCH`: ADT and claims admit timestamps differ by more than `timestamp_tolerance_hours` (default 24)
- [ ] Flag is added to encounter's `confidence_flags` array
- [ ] Tolerance is configurable per customer
- [ ] Unit test: ADT admit 10:00 Jan 1, claims admit 15:00 Jan 2 (29h diff) with tolerance 24h → TIMESTAMP_MISMATCH
- [ ] Unit test: ADT admit 10:00, claims admit 11:00 (1h diff) → no flag

### US-005: Flag missing event patterns
**Description:** As a developer, I need common data quality issues flagged automatically.

**Acceptance Criteria:**
- [ ] `MISSING_DISCHARGE`: admit event present but no discharge event (and encounter open > 48h)
- [ ] `ORPHAN_DISCHARGE`: discharge event with no matching admit event
- [ ] `CLAIMS_ONLY_ENCOUNTER`: encounter has claims events but zero ADT events
- [ ] `ADT_ONLY_ENCOUNTER`: encounter has ADT events but zero claims (beyond expected claims lag)
- [ ] `AUTH_WITHOUT_ADMIT`: auth signal with no matching encounter
- [ ] Each flag added to encounter's `confidence_flags` array
- [ ] Unit tests for each flag condition

### US-006: Implement ReconcileStage
**Description:** As a developer, I need the reconcile stage to plug into the pipeline runner.

**Acceptance Criteria:**
- [ ] `asre/reconcile/stage.py` defines `ReconcileStage` implementing `PipelineStage`
- [ ] Processes list of encounters → returns reconciled encounters
- [ ] Records stage metrics: encounters_reconciled, flags_generated (by type), auth_without_admit_count
- [ ] Unit test: batch with mixed-source encounters → correct reconciliation

## Functional Requirements

- FR-01: Timestamp and classification priorities are separate configs (a source can be high priority for timestamps but low for classification)
- FR-02: When a source is missing entirely (e.g., no claims), use the next-highest-priority source
- FR-03: Reconciliation never creates or destroys encounters — it only updates fields on existing encounters
- FR-04: All flags are additive (an encounter can have multiple flags)
- FR-05: Claims lag expectation for ADT_ONLY_ENCOUNTER flag: configurable, default 45 days
- FR-06: Auth matching is by patient_key + facility + time window (same rules as encounter stitching)

## Non-Goals

- No confidence score computation (PRD-09)
- No resolution of flagged issues (flags are informational)
- No user-facing flag descriptions (just machine-readable flag names)

## Technical Considerations

- Reconciliation runs per-encounter (no cross-encounter logic here)
- Auth-without-admit detection requires comparing orphan auth events against all encounters for the patient
- ADT_ONLY_ENCOUNTER flag should consider the claims lookback_buffer — if encounter is newer than claims lag, it's expected to be ADT-only

## TDD Approach

1. Write tests for timestamp selection from multi-source encounters
2. Write tests for classification resolution (encounter_type, DRG, payer)
3. Write tests for auth reconciliation (supporting vs orphan)
4. Write tests for each flag (TIMESTAMP_MISMATCH, MISSING_DISCHARGE, ORPHAN_DISCHARGE, CLAIMS_ONLY, ADT_ONLY, AUTH_WITHOUT_ADMIT)
5. Write golden-file tests: encounters with known multi-source data → known reconciled output
6. Implement to make tests pass

## Success Metrics

- Multi-source encounters correctly reconciled with documented priority rules
- All 6 flags correctly generated from known test data
- Golden-file tests pass for reconciliation scenarios
