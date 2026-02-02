# PRD-07: Deduplication

## Introduction

Build the deduplication stage that removes duplicate events within encounters and merges overlapping encounters. Duplicates arise when the same clinical event appears in multiple source feeds or is re-transmitted.

**SPEC References:** §5.7 (deduplication stage), §4.2 (deduplication config)

## Goals

- Identify and resolve duplicate events within encounters
- Merge overlapping encounters for the same patient at the same facility
- Retain duplicate records for audit trail
- Track deduplication statistics

## Dependencies

- PRD-01 (models)
- PRD-02 (DeduplicationConfig, ReconciliationConfig for source priorities)
- PRD-06 (stitched encounters with assigned events)

## User Stories

### US-001: Identify duplicate events within an encounter
**Description:** As a developer, I need to find events that match on configured fields within a time tolerance.

**Acceptance Criteria:**
- [ ] `asre/dedup/deduplicator.py` defines `Deduplicator` class
- [ ] Within each encounter, compares events pairwise on `match_fields` (default: patient_key, event_type, facility_canonical_id)
- [ ] Events matching on all fields AND within `time_tolerance_minutes` (default: 30) are duplicates
- [ ] Unit test: two ADMIT events 15 minutes apart at same facility → duplicates
- [ ] Unit test: two ADMIT events 45 minutes apart at same facility → not duplicates
- [ ] Unit test: ADMIT and DISCHARGE 15 minutes apart → not duplicates (different event_type)

### US-002: Resolve duplicates by source priority
**Description:** As a developer, I need to keep the highest-priority source event when duplicates are found.

**Acceptance Criteria:**
- [ ] When duplicates found, keep the event from the highest `timestamp_priority` source
- [ ] Priority from config: e.g., ADT=100 > claims=80 > auth=40
- [ ] If same source: keep the earliest ingested record (by `ingested_at`)
- [ ] Unit test: ADT event (priority 100) + claims event (priority 80) as duplicates → keep ADT
- [ ] Unit test: two ADT events → keep the one with earlier ingested_at

### US-003: Mark duplicates for audit
**Description:** As a developer, I need duplicates retained in the detail table with a duplicate role.

**Acceptance Criteria:**
- [ ] Duplicate events are NOT deleted — they remain in the event list
- [ ] Duplicate events have `role_in_encounter = 'duplicate'` set for the detail table
- [ ] The kept event retains its original role (admit_anchor, discharge_anchor, supporting)
- [ ] Unit test: after dedup, duplicate events have role='duplicate', kept event has original role

### US-004: Implement encounter-level dedup
**Description:** As a developer, I need to merge overlapping encounters for the same patient at the same facility.

**Acceptance Criteria:**
- [ ] Two encounters for same patient + same facility with overlapping time ranges → merge into one
- [ ] Overlapping = encounter A's time range overlaps with encounter B's time range
- [ ] Merged encounter takes the earlier admit_ts and later discharge_ts
- [ ] All events from both encounters are combined
- [ ] Merged encounter_id uses the earlier encounter's ID (stability)
- [ ] Unit test: two overlapping encounters → merged into one with combined events

### US-005: Implement DedupStage
**Description:** As a developer, I need the dedup stage to plug into the pipeline runner.

**Acceptance Criteria:**
- [ ] `asre/dedup/stage.py` defines `DedupStage` implementing `PipelineStage`
- [ ] Processes list of encounters → returns deduplicated encounters
- [ ] Records stage metrics: events_before, events_after, duplicates_found, encounters_merged
- [ ] Unit test: batch with known duplicates → correct dedup results

## Functional Requirements

- FR-01: Match fields are configurable per customer (not hardcoded)
- FR-02: Time tolerance is configurable per customer (default 30 minutes)
- FR-03: Source priority for dedup resolution uses `reconciliation.timestamp_priority` from config
- FR-04: Encounter-level dedup runs after event-level dedup
- FR-05: Dedup is deterministic — same inputs always produce same outputs
- FR-06: Track `DUPLICATE_DETECTED` flag on encounters where duplicates were found (used by confidence scoring in PRD-09)

## Non-Goals

- No cross-patient deduplication (duplicates are always within same patient)
- No fuzzy matching for dedup (exact field match only)
- No ML-based duplicate detection

## Technical Considerations

- Event-level dedup is O(n^2) within an encounter, but encounters typically have < 20 events so this is fine
- Encounter-level dedup requires comparing all encounters for a patient — partition by patient first
- Time range overlap calculation: A overlaps B if A.admit_ts <= B.discharge_ts AND B.admit_ts <= A.discharge_ts

## TDD Approach

1. Write tests for duplicate identification (matching fields + time tolerance)
2. Write tests for source priority resolution
3. Write tests for audit trail (duplicate role marking)
4. Write tests for encounter-level merge
5. Write golden-file test: batch with duplicates → known output
6. Implement to make tests pass

## Success Metrics

- Event-level duplicates correctly identified and resolved
- Encounter-level overlaps correctly merged
- Audit trail preserves all original events with correct roles
- Golden-file tests pass
