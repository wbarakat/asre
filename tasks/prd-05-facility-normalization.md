# PRD-05: Facility Normalization

## Introduction

Build the facility normalization pipeline that resolves raw facility name strings to canonical facility IDs. This includes string normalization (preserving campus/directional tokens), a matching cascade (exact → NPI/CCN → fuzzy → new), and facility registry management.

**SPEC References:** §5.4 (facility normalization stage), §7.1 (string normalization pipeline), §7.2 (abbreviation dictionary), §7.3 (matching cascade), §7.4 (public registry integration)

## Goals

- Normalize facility name strings with campus-aware token preservation
- Implement 4-tier matching cascade: exact alias → NPI/CCN → fuzzy → create new
- Manage facility registry with canonical IDs, aliases, and NPI/CCN
- Flag unresolved facilities for human review
- Provide CLI commands for facility management

## Dependencies

- PRD-01 (models)
- PRD-02 (FacilityNormalizationConfig, FacilityAliasConfig)
- PRD-04 (canonical events with `facility_raw` populated)

## User Stories

### US-001: Implement string normalization pipeline
**Description:** As a developer, I need to normalize facility name strings so variant spellings match correctly.

**Acceptance Criteria:**
- [ ] `asre/facility/normalizer.py` defines `FacilityNormalizer` class
- [ ] Pipeline steps (in order): uppercase → strip punctuation → expand abbreviations → remove generic suffixes → normalize whitespace
- [ ] Abbreviation expansion uses configurable dictionary per SPEC §7.2 (MED CTR → MEDICAL CENTER, HOSP → HOSPITAL, etc.)
- [ ] Generic suffixes removed: HOSPITAL, MEDICAL CENTER, HEALTH SYSTEM, HEALTH, CLINIC, CENTER (only when they are trailing organizational suffixes)
- [ ] **Directional tokens PRESERVED:** EAST, WEST, NORTH, SOUTH
- [ ] **Campus tokens PRESERVED:** MAIN, DOWNTOWN, CAMPUS, MIDTOWN, UPTOWN
- [ ] Unit tests:
  - "St. Mary's Med Ctr - East Campus" → "ST MARYS EAST CAMPUS"
  - "Memorial Regional Hospital" → "MEMORIAL REGIONAL"
  - "Good Samaritan Hosp - West" → "GOOD SAMARITAN WEST"
  - "University Health System" → "UNIVERSITY"
  - "North Valley Medical Center" → "NORTH VALLEY"

### US-002: Implement exact alias matching
**Description:** As a developer, I need exact matching against known facility aliases.

**Acceptance Criteria:**
- [ ] `asre/facility/matcher.py` defines `FacilityMatcher` class
- [ ] Loads facility aliases from `FacilityAliasConfig` into an in-memory lookup
- [ ] Exact match: normalized input string matches any alias → return canonical_id
- [ ] Case-insensitive comparison (both sides normalized)
- [ ] Unit test: "ST MARYS MEDICAL CTR" matches alias → returns FAC_001

### US-003: Implement NPI/CCN matching
**Description:** As a developer, I need to match facilities by NPI or CCN when available in source data.

**Acceptance Criteria:**
- [ ] If source record includes NPI, match directly against registry NPI field
- [ ] If source record includes CCN, match directly against registry CCN field
- [ ] NPI/CCN match takes precedence over fuzzy match but not exact alias match
- [ ] Unit test: record with NPI "1234567890" matches facility with that NPI

### US-004: Implement fuzzy matching
**Description:** As a developer, I need fuzzy matching as a fallback when exact and NPI/CCN matching fail.

**Acceptance Criteria:**
- [ ] Uses rapidfuzz `token_sort_ratio` for fuzzy comparison
- [ ] Compares normalized input against all known facility names and aliases
- [ ] Accepts match if score >= `fuzzy_threshold` (default 0.85)
- [ ] If multiple facilities score above threshold, selects highest score
- [ ] Logs match score for audit
- [ ] Unit test: "ST MARYS EAST" fuzzy matches "ST MARYS EAST CAMPUS" above threshold
- [ ] Unit test: "COMPLETELY DIFFERENT NAME" does not match at threshold 0.85

### US-005: Handle unresolved facilities
**Description:** As a developer, I need to create new facility records when no match is found and flag for review.

**Acceptance Criteria:**
- [ ] When no match found at any tier: create new facility record
- [ ] New facility gets auto-generated `facility_canonical_id`
- [ ] Facility marked with flag `FACILITY_NEW_UNREVIEWED`
- [ ] New facility's normalized name becomes its first alias
- [ ] Subsequent events with same normalized name match the new facility (don't create duplicates)
- [ ] Unit test: unknown facility creates new record; second event with same name reuses it

### US-006: Implement facility registry
**Description:** As a developer, I need a registry that stores canonical facilities with aliases, NPI, CCN, and facility type.

**Acceptance Criteria:**
- [ ] `asre/facility/registry.py` defines `FacilityRegistry` class
- [ ] Loads initial data from `facility_aliases.yaml`
- [ ] In-memory index keyed by: normalized alias strings, NPI, CCN
- [ ] Supports adding new facilities and aliases at runtime
- [ ] Can persist to database table (`asre_facility_registry`)
- [ ] Tracks `facility_type`: acute, ltach, snf, rehab, psych, ed_standalone
- [ ] Unit test: load registry, lookup by alias, lookup by NPI, add new facility

### US-007: Implement FacilityNormalizationStage
**Description:** As a developer, I need the facility normalization stage to plug into the pipeline.

**Acceptance Criteria:**
- [ ] `asre/facility/stage.py` defines `FacilityNormalizationStage` implementing `PipelineStage`
- [ ] Processes each canonical event: normalizes `facility_raw` → matches → sets `facility_canonical_id`
- [ ] Updates facility registry with any new facilities
- [ ] Records stage metrics: matched (exact, npi, fuzzy, new), errors
- [ ] Unit test: batch of events with various facility names → correct canonical IDs assigned

### US-008: Add facility CLI commands
**Description:** As a developer, I need CLI commands to manage unresolved facilities.

**Acceptance Criteria:**
- [ ] `asre facilities --unresolved` lists facilities flagged FACILITY_NEW_UNREVIEWED
- [ ] `asre facilities resolve <id>` maps unresolved facility to existing canonical ID (placeholder for manual resolution workflow)
- [ ] Commands read from facility registry in database

## Functional Requirements

- FR-01: Abbreviation dictionary is configurable per customer (loaded from config, not hardcoded)
- FR-02: Matching cascade order is strict: exact alias → NPI/CCN → fuzzy → new (never skip tiers)
- FR-03: Fuzzy threshold is configurable (default 0.85 from SPEC §4.2)
- FR-04: New facilities created during a run are immediately available for matching subsequent events in the same batch
- FR-05: Facility canonical_id format: `FAC_` + padded sequence number or UUID
- FR-06: Registry supports multiple aliases per facility (per SPEC §7.4 example)
- FR-07: The dbt model `asre_facility_registry.sql` materializes the registry as a warehouse table

## Non-Goals

- No public NPI/CCN registry file downloads (registry data is provided via facility_aliases.yaml in v1)
- No web UI for facility review
- No ML-based matching

## Technical Considerations

- rapidfuzz `token_sort_ratio` handles word reordering well (e.g., "EAST ST MARYS" vs "ST MARYS EAST")
- Registry should be loaded once at stage start, not per-event (performance)
- Consider caching normalized strings to avoid re-normalizing the same facility_raw multiple times in a batch
- dbt model for facility registry is a simple full-refresh from the Python-managed table

## TDD Approach

1. Write tests for string normalizer (each step, each abbreviation, directional preservation)
2. Write tests for exact alias matching
3. Write tests for fuzzy matching (above/below threshold, multiple candidates)
4. Write tests for new facility creation and dedup
5. Write tests for the full matching cascade
6. Write golden-file tests: known facility strings → known canonical IDs
7. Implement to make tests pass

## Success Metrics

- "St. Mary's Med Ctr - East Campus" and "ST MARYS EAST CAMPUS" resolve to same facility
- "St. Mary's East" and "St. Mary's West" resolve to DIFFERENT facilities
- Unresolved facilities are created and flagged correctly
- Golden-file tests pass for all normalization scenarios
