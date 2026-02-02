# PRD-06: Encounter Stitching

## Introduction

Build the encounter stitching algorithm — the core domain logic that groups canonical events into encounters. This is the most complex algorithm in ASRE, handling time windowing, facility matching, patient class transitions, transfer chain detection, cancellations, and deterministic encounter ID generation.

**SPEC References:** §5.5 (encounter stitching), §5.6 (encounter ID stability and edge cases), §4.2 (encounter_stitching config)

## Goals

- Group canonical events into encounters by patient, facility, and time window
- Handle all patient class transitions (ED→IP, OBS→IP, IP→IP)
- Detect transfer chains across facilities
- Handle cancellation events
- Generate stable, deterministic encounter IDs

## Dependencies

- PRD-01 (models: CanonicalEvent, Encounter)
- PRD-02 (EncounterStitchingConfig)
- PRD-05 (facility-normalized events with `facility_canonical_id`)

## User Stories

### US-001: Implement basic encounter stitching
**Description:** As a developer, I need events grouped into encounters by patient, facility, and time window.

**Acceptance Criteria:**
- [ ] `asre/stitch/encounter_stitcher.py` defines `EncounterStitcher` class
- [ ] Partitions events by `patient_key`
- [ ] Sorts by `event_ts` ascending
- [ ] Tiebreaker for identical `event_ts`: source type priority from config `same_timestamp_tiebreaker` (default: claims > ADT > auth)
- [ ] Events within `time_window_hours` (default 48) of current encounter's last event AND same facility → stitch into same encounter
- [ ] Events outside time window OR different facility → close current encounter, start new
- [ ] Unit tests:
  - Two ADT events 4 hours apart at same facility → one encounter
  - Two ADT events 72 hours apart at same facility → two encounters
  - Two ADT events 4 hours apart at different facilities → two encounters

### US-002: Implement facility matching requirement
**Description:** As a developer, I need configurable facility matching so events at different facilities create separate encounters.

**Acceptance Criteria:**
- [ ] When `facility_must_match = true` (default), events must share `facility_canonical_id` to stitch
- [ ] When `facility_must_match = false`, facility is ignored during stitching (time window only)
- [ ] Null facility_canonical_id: treated as non-matching (events with unresolved facilities don't auto-stitch)
- [ ] Unit test: facility_must_match=true → separate encounters for different facilities
- [ ] Unit test: facility_must_match=false → same encounter regardless of facility

### US-003: Implement ED→IP merge
**Description:** As a developer, I need ED arrival followed by inpatient admission at the same facility to merge into a single encounter.

**Acceptance Criteria:**
- [ ] ED_ARRIVAL + ADMIT at same facility within time window → single encounter
- [ ] Encounter type = `inpatient` (IP takes precedence over ED)
- [ ] ED events are kept as supporting events in the encounter
- [ ] Based on `patient_class_transitions: [{from: "ed", to: "inpatient", action: "merge"}]`
- [ ] Unit test: ED_ARRIVAL at 10:00 + ADMIT at 14:00 same facility → one encounter, type=inpatient

### US-004: Implement OBS→IP conversion
**Description:** As a developer, I need observation-to-inpatient conversions to merge into a single encounter with a flag.

**Acceptance Criteria:**
- [ ] OBS_START + OBS_TO_IP at same facility within time window → single encounter
- [ ] Sets `obs_to_ip_conversion = true` on the encounter
- [ ] Encounter type = `inpatient`
- [ ] Based on `patient_class_transitions: [{from: "observation", to: "inpatient", action: "merge"}]`
- [ ] Unit test: OBS_START + OBS_TO_IP → one encounter with obs_to_ip_conversion=true

### US-005: Implement IP→IP as new encounter
**Description:** As a developer, I need same-day inpatient readmission at the same facility to create a new encounter (not merge).

**Acceptance Criteria:**
- [ ] DISCHARGE + new ADMIT (both IP) at same facility within time window → two separate encounters
- [ ] Based on `patient_class_transitions: [{from: "inpatient", to: "inpatient", action: "new_encounter"}]`
- [ ] Unit test: IP discharge at 10:00 + IP admit at 14:00 same facility → two encounters

### US-006: Implement transfer chain detection
**Description:** As a developer, I need to detect and link encounters across facilities when transfers occur.

**Acceptance Criteria:**
- [ ] Discharge from Facility A within `time_window_hours` of admit at Facility B → transfer chain
- [ ] Each facility segment is its own encounter (separate encounter_ids)
- [ ] Both encounters' `transfer_chain` array contains both encounter_ids, ordered by time
- [ ] Supports multi-hop transfers: A → B → C → three encounters, all linked
- [ ] Unit test: discharge at Facility A, admit at Facility B 2 hours later → two encounters linked in transfer_chain
- [ ] Unit test: A → B → C chain → three encounters, all share same transfer_chain array

### US-007: Handle cancellation events
**Description:** As a developer, I need cancellation events to update encounter status correctly.

**Acceptance Criteria:**
- [ ] CANCEL_ADMIT: marks encounter `status = cancelled`
- [ ] CANCEL_DISCHARGE: removes discharge_ts, sets status back to `open` (encounter reopened)
- [ ] Cancel events are attached to the most recent matching encounter for the patient at that facility
- [ ] Unit test: ADMIT + CANCEL_ADMIT → encounter status=cancelled
- [ ] Unit test: ADMIT + DISCHARGE + CANCEL_DISCHARGE → encounter status=open, discharge_ts=null

### US-008: Generate deterministic encounter IDs
**Description:** As a developer, I need encounter IDs that are stable across re-processing runs.

**Acceptance Criteria:**
- [ ] `encounter_id = hash(patient_key + facility_canonical_id + first_admit_source_record_id)`
- [ ] Same inputs always produce same encounter_id (verified across runs)
- [ ] Hash function produces a URL-safe string (e.g., SHA-256 hex digest, truncated)
- [ ] Unit test: same patient + facility + source_record_id → same encounter_id every time
- [ ] Unit test: different source_record_id → different encounter_id

### US-009: Set encounter metadata
**Description:** As a developer, I need each encounter to have correctly derived metadata fields.

**Acceptance Criteria:**
- [ ] `encounter_type` derived from events: inpatient, observation, ed_only, outpatient
  - If any IP event → inpatient
  - If OBS events but no IP → observation
  - If only ED events → ed_only
  - Otherwise → outpatient
- [ ] `status`: open (no discharge), closed (has discharge), cancelled
- [ ] `admit_ts`: earliest admit/arrival event timestamp
- [ ] `discharge_ts`: latest discharge event timestamp (null if open)
- [ ] `los_hours`: discharge_ts - admit_ts in hours (null if open)
- [ ] `source_event_ids`: list of all canonical event_ids in encounter
- [ ] `source_systems`: distinct source_system values from events
- [ ] `has_adt`, `has_claims`, `has_auth`: derived from source_systems
- [ ] Unit test: encounter with ADT admit + claims discharge → has_adt=true, has_claims=true, has_auth=false

### US-010: Implement StitchStage
**Description:** As a developer, I need the stitch stage to plug into the pipeline runner.

**Acceptance Criteria:**
- [ ] `asre/stitch/stage.py` defines `StitchStage` implementing `PipelineStage`
- [ ] Processes EventBatch of canonical events → produces list of Encounters
- [ ] Records stage metrics: events_in, encounters_out, transfers_detected, cancellations_processed
- [ ] Unit test: full batch processing end-to-end

## Functional Requirements

- FR-01: Events with identical event_ts are ordered by source type priority (configurable)
- FR-02: Encounters with no admit event (discharge-only) are created with `admit_ts` from the earliest event
- FR-03: Overlapping encounters at different facilities are allowed (patient transferred same day)
- FR-04: Transfer chain detection is based on timing only (discharge → admit within window at different facility)
- FR-05: Patient class transition rules are configurable per customer
- FR-06: Encounter type can change during stitching (e.g., starts as ED, becomes IP after merge)

## Non-Goals

- No deduplication (PRD-07)
- No cross-source reconciliation (PRD-08)
- No confidence scoring (PRD-09)
- No readmission detection (PRD-10)

## Technical Considerations

- Stitching is O(n log n) per patient (sort + single pass). Should handle 100K events per patient efficiently.
- Transfer chain detection requires a second pass after initial stitching (compare encounters across facilities)
- Cancellation handling modifies in-place — ensure the stitcher doesn't create a new encounter for cancel events
- Consider building an `EncounterBuilder` helper class to accumulate events and compute derived fields

## TDD Approach

1. Write tests for basic stitching (same patient, time window, facility)
2. Write tests for each patient class transition (ED→IP, OBS→IP, IP→IP)
3. Write tests for transfer chain detection (2-hop, 3-hop)
4. Write tests for cancellation handling
5. Write tests for deterministic encounter ID generation
6. Write tests for encounter metadata derivation
7. Write golden-file tests for complex scenarios (mixed sources, transitions, transfers)
8. Implement to make tests pass

## Success Metrics

- All edge cases from SPEC §5.6 have passing tests
- Same input data produces identical encounters on repeated runs
- Transfer chains correctly link encounters across facilities
- Golden-file tests cover: basic stitching, ED→IP merge, OBS→IP conversion, transfer chain, cancellation, multi-patient batch
