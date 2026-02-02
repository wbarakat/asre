# PRD-02: Configuration System

## Introduction

Build the YAML configuration loading and validation system that drives all ASRE behavior. Every pipeline stage reads its parameters from config — stitching windows, scoring weights, facility thresholds, source field mappings, etc. This PRD also establishes the CLI skeleton.

**SPEC References:** §4.1 (mapping config format), §4.2 (global customer config), §13.2 (environment variables), §13.3 (CLI), §14.3 (encryption/env var substitution)

## Goals

- Define Pydantic models for all configuration schemas
- Implement YAML loader with `${ENV_VAR}` substitution
- Provide clear validation error messages with field paths
- Create example customer config for testing
- Establish CLI skeleton with `validate-config` command

## Dependencies

- PRD-01 (core models for type references)

## User Stories

### US-001: Define global config Pydantic schema
**Description:** As a developer, I need typed config models so invalid configurations are caught at load time.

**Acceptance Criteria:**
- [ ] `asre/config/schema.py` defines Pydantic models for all sections of SPEC §4.2:
  - `CustomerConfig` (name, id)
  - `WarehouseConfig` (type, schema_prefix)
  - `ScheduleConfig` (mode, frequency, lookback_buffer per source type with default)
  - `EncounterStitchingConfig` (time_window_hours, facility_must_match, same_timestamp_tiebreaker, patient_class_transitions, stale_encounter_thresholds)
  - `DeduplicationConfig` (time_tolerance_minutes, match_fields)
  - `ReconciliationConfig` (timestamp_priority per source, classification_priority per source, timestamp_tolerance_hours)
  - `EpisodeStitchingConfig` (enabled, rules with all windows, condition_grouper, episode_confidence method)
  - `FacilityNormalizationConfig` (fuzzy_threshold, alias_file, use_npi_registry, use_ccn_registry)
  - `ConfidenceScoringConfig` (weights dict, penalties dict)
  - `AlertingConfig` (enabled, channels, thresholds)
  - `GlobalConfig` (top-level combining all above)
- [ ] All fields have proper types and defaults matching SPEC defaults
- [ ] Unit tests verify valid config loads and invalid config raises ValidationError

### US-002: Define source config Pydantic schema
**Description:** As a developer, I need typed models for per-source mapping configs (ADT, claims, auth).

**Acceptance Criteria:**
- [ ] Pydantic models for source configs per SPEC §4.1:
  - `SourceDefinition` (name, type, table, incremental_key)
  - `FieldMappings` (patient_key, event_ts, event_type, facility_raw, source_record_id, patient_class, payer_id, drg, principal_diagnosis, admitting_diagnosis, diagnosis_codes — most optional)
  - `EventTypeRules` (admit_flag expr, discharge_flag expr, event_type_map with conditional rules)
  - `PairedEvents` (admit and discharge sub-configs for claims)
  - `PatientClassRules` (condition → class mapping list)
  - `AuthStatusMap` (code → status mapping)
  - `FiltersConfig` (exclude expression)
  - `SourceConfig` (top-level combining all above)
- [ ] Source type validation: `type` must be one of `adt`, `claims`, `auth`
- [ ] Claims sources must have `paired_events` defined
- [ ] Auth sources must have `auth_status_map` defined
- [ ] Unit tests for each source type (ADT, claims, auth)

### US-003: Define facility alias config schema
**Description:** As a developer, I need a schema for the facility aliases YAML file.

**Acceptance Criteria:**
- [ ] Pydantic model for facility alias config per SPEC §7.4:
  - `FacilityAlias` (canonical_id, canonical_name, npi, ccn, aliases list)
  - `FacilityAliasConfig` (facilities list)
- [ ] Unit test verifies valid and invalid alias configs

### US-004: Implement YAML config loader
**Description:** As a developer, I need to load customer configs from the filesystem with env var substitution.

**Acceptance Criteria:**
- [ ] `asre/config/loader.py` provides `load_config(config_path: str, customer_id: str) -> GlobalConfig`
- [ ] Discovers and loads `config.yaml` from `<config_path>/<customer_id>/`
- [ ] Discovers and loads all `sources/*.yaml` files
- [ ] Discovers and loads `facility_aliases.yaml` if present
- [ ] `${ENV_VAR}` patterns in YAML values are substituted from environment
- [ ] Missing env var raises clear error with the variable name
- [ ] Returns fully validated `GlobalConfig` with attached source configs
- [ ] Unit tests: valid load, missing file, missing env var, malformed YAML

### US-005: Create example customer config
**Description:** As a developer, I need a complete example config for use in all subsequent PRD tests.

**Acceptance Criteria:**
- [ ] `customer_config/test_customer/config.yaml` with all sections populated per SPEC §4.2
- [ ] `customer_config/test_customer/sources/adt_vendor_x.yaml` per SPEC §4.1 ADT example
- [ ] `customer_config/test_customer/sources/claims_clearinghouse.yaml` per SPEC §4.1 claims example
- [ ] `customer_config/test_customer/sources/auth_portal.yaml` per SPEC §4.1 auth example
- [ ] `customer_config/test_customer/facility_aliases.yaml` with sample facilities
- [ ] All example configs pass validation

### US-006: Implement CLI skeleton
**Description:** As a developer, I need a CLI entry point so I can run ASRE commands.

**Acceptance Criteria:**
- [ ] `asre/cli/main.py` uses Click framework
- [ ] `asre validate-config` loads and validates config, prints success or errors
- [ ] `asre test-connection` placeholder (prints "not yet implemented")
- [ ] `asre` with no args shows help
- [ ] CLI reads `ASRE_CONFIG_PATH` and `ASRE_CUSTOMER_ID` from environment or `--config-path` / `--customer-id` flags
- [ ] Entry point registered in `pyproject.toml` so `asre` command works after install

## Functional Requirements

- FR-01: Config validation must report ALL errors at once (not fail on first error)
- FR-02: `${ENV_VAR}` substitution works in any string value at any nesting depth
- FR-03: Default values match SPEC exactly (e.g., `time_window_hours: 48`, `fuzzy_threshold: 0.85`)
- FR-04: Source configs are validated against their `type` — claims must have `paired_events`, auth must have `auth_status_map`
- FR-05: `lookback_buffer` supports per-source-type overrides with a `default` fallback
- FR-06: `patient_class_transitions` is a list of `{from, to, action}` where action is `merge` or `new_encounter`
- FR-07: `stale_encounter_thresholds` supports per-facility-type values with a `default` fallback
- FR-08: Confidence scoring weights and penalties are arbitrary string→number dicts (customer can add custom flags)

## Non-Goals

- No config hot-reloading (config is loaded once at pipeline start)
- No config UI or web editor
- No warehouse connectivity (just the `test-connection` placeholder)
- No pipeline execution

## Technical Considerations

- Use Pydantic v2 with `model_validator` for cross-field validation
- Duration strings (e.g., "2h", "45d") need a custom parser → convert to timedelta or hours
- Event type rules use simple expression strings (not full SQL) — these are evaluated in Python during canonicalization
- Config loader should be importable for use in tests: `load_config("customer_config", "test_customer")`

## TDD Approach

1. Write tests for each Pydantic model with valid and invalid inputs
2. Write tests for env var substitution (set/unset vars)
3. Write tests for config discovery (correct files found in directory)
4. Write tests for CLI commands (Click test runner)
5. Implement to make tests pass

## Success Metrics

- `asre validate-config` succeeds with example config
- `asre validate-config` with deliberately broken config prints clear errors
- All config permutations from SPEC are representable and validatable
