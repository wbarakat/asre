# PRD-04: Canonicalize and Event Type Resolution

## Introduction

Build the canonicalization stage that maps diverse source schemas (ADT, claims, auth) to the single `CanonicalEvent` schema. This includes field mapping, event type resolution from HL7 triggers and patient class, paired event emission for claims, diagnosis field mapping, and auth status mapping.

**SPEC References:** §3.2 (canonical event model), §3.3 (normalized event types), §4.1 (mapping config examples), §5.3 (canonicalize stage)

## Goals

- Map source columns to canonical schema using config-defined field mappings
- Resolve event types from HL7 trigger codes + patient class conditions
- Emit paired admit/discharge events from single claims rows
- Map diagnosis codes for claims sources
- Handle auth status code mapping
- Gracefully skip unparseable records (event-level error tolerance)

## Dependencies

- PRD-01 (CanonicalEvent model, EventBatch, pipeline stage interface)
- PRD-02 (SourceConfig with field_mappings, event_type_rules, paired_events)
- PRD-03 (ingested raw records as list[dict])

## User Stories

### US-001: Implement field mapper
**Description:** As a developer, I need to map source columns to canonical event fields using config-defined mappings.

**Acceptance Criteria:**
- [ ] `asre/canonicalize/mapper.py` defines `FieldMapper` class
- [ ] Takes raw record dict + `FieldMappings` config
- [ ] Maps each configured source column to its canonical field
- [ ] Generates `event_id` as UUID for each canonical event
- [ ] Sets `ingested_at` to current timestamp
- [ ] Sets `batch_id` from pipeline context
- [ ] Sets `source_system` from source config name
- [ ] Unmapped optional fields are set to None
- [ ] Unit test: ADT record mapped correctly with all fields

### US-002: Implement event type resolver for ADT
**Description:** As a developer, I need to resolve HL7 event types + patient class into normalized ASRE event types.

**Acceptance Criteria:**
- [ ] `asre/canonicalize/event_type_resolver.py` defines `EventTypeResolver` class
- [ ] Implements conditional mapping from SPEC §4.1 `event_type_map`:
  - A01 + IP class → ADMIT
  - A01 + OBS class → OBS_START
  - A01 + ED class → ED_ARRIVAL (A04 equivalent)
  - A03 default → DISCHARGE
  - A03 + ED class → ED_DEPARTURE
  - A03 + OBS class → OBS_END
  - A02 → TRANSFER_IN
  - A06 → OBS_TO_IP
  - A11 → CANCEL_ADMIT
  - A13 → CANCEL_DISCHARGE
- [ ] Sets `admit_flag` and `discharge_flag` based on `admit_flag` / `discharge_flag` expressions in config
- [ ] All 16 event types from SPEC §3.3 are supported
- [ ] Unit tests for each event type mapping

### US-003: Implement paired event emission for claims
**Description:** As a developer, I need claims rows to produce two canonical events (admit + discharge).

**Acceptance Criteria:**
- [ ] When source config has `paired_events`, one source row emits two CanonicalEvents
- [ ] Admit event: uses `paired_events.admit.event_ts` column, `event_type=CLAIM_ADMIT`, `admit_flag=True`
- [ ] Discharge event: uses `paired_events.discharge.event_ts` column, `event_type=CLAIM_DISCHARGE`, `discharge_flag=True`
- [ ] Both events share the same `source_record_id`, `patient_key`, `facility_raw`
- [ ] Each event gets its own unique `event_id`
- [ ] Unit test: one claims row → two canonical events with correct types and timestamps

### US-004: Implement patient class resolution for claims
**Description:** As a developer, I need to derive patient_class from claims bill type codes.

**Acceptance Criteria:**
- [ ] When source config has `patient_class_rules`, evaluate conditions in order
- [ ] First matching condition sets `patient_class` on the canonical event
- [ ] Conditions support SQL-like expressions (e.g., `bill_type_code LIKE '11%'`)
- [ ] If no condition matches, `patient_class` is null
- [ ] Unit test: bill_type_code '111' → inpatient, '131' → outpatient, '999' → null

### US-005: Implement diagnosis code mapping
**Description:** As a developer, I need to map claims diagnosis fields to canonical format.

**Acceptance Criteria:**
- [ ] Maps `principal_diagnosis` field from source to canonical event
- [ ] Maps `admitting_diagnosis` if configured
- [ ] Maps `diagnosis_codes` field — handles both JSON array and delimited string formats
- [ ] Each diagnosis code becomes a `DiagnosisCode` object with code, type, sequence, poa
- [ ] Unit test: claims row with multiple diagnoses → correct DiagnosisCode list

### US-006: Implement auth status mapping
**Description:** As a developer, I need to map auth status codes to standardized values.

**Acceptance Criteria:**
- [ ] When source config has `auth_status_map`, map source status code to canonical value
- [ ] Maps to: approved, denied, pending, modified (per SPEC §4.1 auth example)
- [ ] Derives event_type from mapped status: approved → AUTH_APPROVED, denied → AUTH_DENIED, pending → AUTH_REQUESTED
- [ ] Sets `auth_flag = True` on all auth events
- [ ] Unit test: auth record with status "A" → auth_status=approved, event_type=AUTH_APPROVED

### US-007: Implement error tolerance for unparseable records
**Description:** As a developer, I need the canonicalize stage to skip bad records without blocking the pipeline.

**Acceptance Criteria:**
- [ ] If a required field (patient_key, event_ts) is missing or null, the record is skipped
- [ ] Skipped records are logged with error details (source_record_id, reason)
- [ ] Skipped records are counted in stage metrics as `errors`
- [ ] Pipeline continues processing remaining records
- [ ] Unit test: batch with 10 records, 2 with missing patient_key → 8 canonical events + 2 errors

### US-008: Implement CanonicalizeStage
**Description:** As a developer, I need the canonicalize stage to plug into the pipeline runner.

**Acceptance Criteria:**
- [ ] `asre/canonicalize/stage.py` defines `CanonicalizeStage` implementing `PipelineStage`
- [ ] Processes raw record dicts from ingest stage
- [ ] Routes records to correct mapping logic based on source type (ADT, claims, auth)
- [ ] Returns `EventBatch` with all canonical events
- [ ] Records stage metrics: records_in, records_out (including paired expansion), errors
- [ ] Unit test: mixed batch of ADT + claims + auth records → correct canonical events

## Functional Requirements

- FR-01: Field mapper must not crash on unexpected source columns (ignore extra columns)
- FR-02: Event type resolver conditions are evaluated in order; first match wins
- FR-03: Claims paired events must preserve `_raw_payload` on both emitted events
- FR-04: Diagnosis codes support ICD-10-CM (dx) and ICD-10-PCS (px) code types
- FR-05: All 16 event types from SPEC §3.3 must be producible by the resolver
- FR-06: `event_id` is a UUID4 string, generated fresh for each canonical event
- FR-07: `source_record_id` for paired claims events: use the same source_record_id on both (they trace to the same source row)

## Non-Goals

- No facility normalization (PRD-05 — `facility_canonical_id` stays null here)
- No encounter stitching
- No expression evaluation engine (use simple string matching for conditions in v1)

## Technical Considerations

- Condition evaluation in event_type_rules: start simple with string-contains and IN-list checks. Avoid building a full SQL expression parser.
- Consider a small expression evaluator for `when` conditions that supports: `field IN (...)`, `field == 'value'`, `field LIKE 'pattern%'`
- Paired events for claims mean `records_out > records_in` is expected and normal

## TDD Approach

1. Write tests for FieldMapper with ADT source
2. Write tests for EventTypeResolver with each HL7 trigger + patient class combo
3. Write tests for paired event emission (claims)
4. Write tests for diagnosis code mapping
5. Write tests for auth status mapping
6. Write tests for error tolerance (missing required fields)
7. Write golden-file tests: known input records → known canonical events
8. Implement to make tests pass

## Success Metrics

- All 16 event types correctly derivable from source data
- Claims row produces exactly 2 canonical events
- Error tolerance: 2% bad records don't block the other 98%
- Golden-file tests pass for ADT, claims, and auth source types
