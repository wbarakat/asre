# PRD: Synthetic Test Data for ASRE Pipeline

## Introduction

ASRE's pipeline stages (ingest through quality check) need realistic healthcare data to validate end-to-end correctness. Currently, tests use minimal inline fixtures with 2-3 events. This PRD defines a synthetic data generation layer that produces realistic ADT, claims, authorization, and eligibility source data -- including deliberately dirty/malformed records -- to exercise every pipeline path. The data is generated via Python factories (Faker-based) for flexibility, plus a curated static dataset for golden-file regression testing. All data loads via pytest (in-memory or test Postgres).

## Goals

- Generate 200+ synthetic patient scenarios covering the full spectrum of encounter types, edge cases, and error conditions
- Provide reusable Faker-based factory functions that produce randomized but deterministic (seeded) source rows for ADT, claims, auth, and eligibility
- Include a hand-crafted static "golden" dataset with known expected outputs for regression testing
- Include deliberately dirty/malformed records (missing fields, invalid dates, duplicates, denied claims, unknown facilities) to test error tolerance
- Enable both unit-level (in-memory) and integration-level (test Postgres) usage via pytest fixtures
- Align all generated data with the existing source config schemas (`adt_vendor_x.yaml`, `claims_clearinghouse.yaml`, `auth_portal.yaml`)

## User Stories

### US-SD-001: Create base patient factory
**Description:** As a test author, I want a factory that generates realistic patient identities so that I can build multi-source scenarios around consistent patient keys.

**Acceptance Criteria:**
- [ ] `tests/factories/patients.py` with `PatientFactory` class
- [ ] Generates: patient_key (MRN format), name, DOB, gender, payer_id
- [ ] Accepts a seed for deterministic output
- [ ] Can generate N patients in batch via `PatientFactory.batch(n, seed=42)`
- [ ] Default batch of 200+ patients with realistic distributions (age, gender, payer mix)
- [ ] Typecheck passes, tests green

### US-SD-002: Create ADT event factory
**Description:** As a test author, I want a factory that generates raw ADT rows matching the `raw_adt_events` table schema so that I can test the ingest and canonicalize stages.

**Acceptance Criteria:**
- [ ] `tests/factories/adt.py` with `ADTEventFactory` class
- [ ] Generates rows with columns: `patient_mrn`, `message_ts`, `message_control_id`, `sending_facility`, `hl7_event`, `patient_class`, `facility_npi`
- [ ] Supports all HL7 event types: A01, A02, A03, A04, A05, A06, A07, A11, A12, A13
- [ ] Patient class codes: E (ED), I (inpatient), O (observation), P (pre-admit)
- [ ] `message_ts` timestamps are realistic (within business hours, proper sequencing for admit->discharge)
- [ ] `sending_facility` drawn from a pool of ~20 realistic hospital names
- [ ] `facility_npi` is a valid 10-digit NPI format
- [ ] Typecheck passes, tests green

### US-SD-003: Create claims event factory
**Description:** As a test author, I want a factory that generates raw claims rows matching the `raw_claims` table schema so that I can test paired event emission and claims canonicalization.

**Acceptance Criteria:**
- [ ] `tests/factories/claims.py` with `ClaimsFactory` class
- [ ] Generates rows with columns: `member_id`, `admission_date`, `discharge_date`, `claim_id`, `facility_name`, `claim_type`, `bill_type_code`, `payer_code`, `drg_code`, `primary_dx`, `all_diagnosis_codes`, `billing_npi`, `claim_status`
- [ ] `bill_type_code` follows real UB-04 patterns (11x=IP, 13x=OP, 85x=ED)
- [ ] `drg_code` drawn from common MS-DRG codes (e.g., 470, 871, 291, 192, 690)
- [ ] `primary_dx` and `all_diagnosis_codes` use realistic ICD-10-CM codes
- [ ] `claim_status` distribution: ~85% PAID, ~10% PENDING, ~5% DENIED
- [ ] `admission_date` < `discharge_date` (except in dirty records)
- [ ] Typecheck passes, tests green

### US-SD-004: Create authorization event factory
**Description:** As a test author, I want a factory that generates raw authorization rows matching the `raw_authorizations` table schema so that I can test auth status mapping.

**Acceptance Criteria:**
- [ ] `tests/factories/auth.py` with `AuthFactory` class
- [ ] Generates rows with columns: `member_id`, `auth_date`, `auth_id`, `servicing_facility`, `auth_type`, `auth_status_code`, `payer_code`
- [ ] `auth_type` values: INITIAL, APPROVED, DENIED, MODIFIED
- [ ] `auth_status_code` values: A, D, P, M with realistic distributions (~70% A, ~10% D, ~15% P, ~5% M)
- [ ] Auth dates align with corresponding ADT/claims dates for the same patient (auth typically precedes or coincides with admit)
- [ ] Typecheck passes, tests green

### US-SD-005: Create facility name pool with variants
**Description:** As a test author, I want a pool of facility names with known aliases and variants so that I can test facility normalization and fuzzy matching.

**Acceptance Criteria:**
- [ ] `tests/factories/facilities.py` with `FacilityPool` class
- [ ] Pool of ~20 canonical facilities with realistic names, NPI, CCN, facility type (acute, LTACH, SNF, rehab, psych)
- [ ] Each facility has 2-4 known aliases (abbreviations, misspellings, old names): e.g., "St. Mary's Medical Center" / "ST MARYS MED CTR" / "Saint Mary's Hospital" / "St Mary Medical Ctr"
- [ ] Factories draw from this pool for consistent cross-source facility references
- [ ] Some facilities intentionally have NO aliases (to test unresolved facility path)
- [ ] Typecheck passes, tests green

### US-SD-006: Create dirty/malformed record generators
**Description:** As a test author, I want factories that produce deliberately bad records so that I can test error tolerance and edge case handling.

**Acceptance Criteria:**
- [ ] `tests/factories/dirty.py` with functions that corrupt valid factory output
- [ ] Missing required fields: `null_field(record, field_name)` — sets a required field to None
- [ ] Invalid timestamps: `corrupt_timestamp(record)` — sets event_ts to unparseable string or future date
- [ ] Reversed dates: `reverse_dates(claims_record)` — discharge_date before admission_date
- [ ] Duplicate records: `duplicate_record(record, n=2)` — exact duplicates with same source_record_id
- [ ] Near-duplicate records: `near_duplicate(record)` — same event, slightly different timestamp (within dedup tolerance)
- [ ] Unknown facility: `unknown_facility(record)` — facility name not in the facility pool
- [ ] Invalid event codes: `invalid_event_type(adt_record)` — hl7_event set to unsupported code (e.g., "Z99")
- [ ] Denied claims: already handled by ClaimsFactory distribution, but `force_denied(claims_record)` for targeted testing
- [ ] Each corruption function returns the modified record + a description of what was corrupted
- [ ] Typecheck passes, tests green

### US-SD-007: Create scenario builders for common encounter patterns
**Description:** As a test author, I want pre-built scenario generators for common healthcare encounter patterns so that I don't have to manually construct multi-event sequences.

**Acceptance Criteria:**
- [ ] `tests/factories/scenarios.py` with `ScenarioBuilder` class
- [ ] `simple_inpatient(patient)` — ADT A01 admit + A03 discharge + matching claim
- [ ] `ed_to_inpatient(patient)` — ADT A01(E) ED arrival + A06 OBS-to-IP + A03(I) discharge + claim
- [ ] `observation_stay(patient)` — ADT A01(O) + A03(O) + claim with 13x bill type
- [ ] `transfer_chain(patient, n_facilities=2)` — discharge from facility A, admit at facility B within transfer window
- [ ] `readmission(patient, days_between=15)` — two separate encounters at same facility within readmission window
- [ ] `cancelled_admit(patient)` — A01 followed by A11 (cancel admit)
- [ ] `claims_only_encounter(patient)` — claim with no corresponding ADT events
- [ ] `adt_only_encounter(patient)` — ADT events with no matching claim
- [ ] `orphan_discharge(patient)` — A03 discharge with no preceding A01 admit
- [ ] `multi_source_conflict(patient)` — ADT and claims with mismatched timestamps (>1 hour difference)
- [ ] `long_stay_ltach(patient, days=45)` — LTACH encounter exceeding acute stale threshold but within LTACH threshold
- [ ] `pre_admit_to_admit(patient)` — A05 pre-admit followed by A01 admit
- [ ] Each scenario returns a dict with `adt_rows`, `claims_rows`, `auth_rows`, and `expected_encounters` (for assertion)
- [ ] Typecheck passes, tests green

### US-SD-008: Generate the 200+ patient master dataset
**Description:** As a test author, I want a single function that generates a complete, seeded dataset of 200+ patients with a realistic mix of encounter scenarios.

**Acceptance Criteria:**
- [ ] `tests/factories/dataset.py` with `generate_master_dataset(seed=42, n_patients=200)` function
- [ ] Returns a `SyntheticDataset` dataclass with: `adt_rows: list[dict]`, `claims_rows: list[dict]`, `auth_rows: list[dict]`, `patients: list[dict]`, `expected_encounter_count: int`
- [ ] Patient scenario distribution (approximate): 40% simple IP, 15% ED-to-IP, 10% observation, 8% transfers, 7% readmissions, 5% claims-only, 5% ADT-only, 3% cancelled, 3% orphan discharge, 2% multi-source conflict, 2% LTACH/SNF long stay
- [ ] ~10% of all records include at least one dirty/malformed element from US-SD-006
- [ ] Deterministic: same seed always produces identical output
- [ ] Total event count in the range of 1500-3000 rows across all sources
- [ ] Typecheck passes, tests green

### US-SD-009: Create pytest fixtures for synthetic data
**Description:** As a test author, I want pytest fixtures that provide the synthetic dataset so that I can use it in integration tests without boilerplate.

**Acceptance Criteria:**
- [ ] `tests/conftest.py` updated (or `tests/integration/conftest.py` created) with fixtures:
  - `synthetic_dataset` — returns the full `SyntheticDataset` from `generate_master_dataset(seed=42)`
  - `synthetic_adt_rows` — just the ADT rows
  - `synthetic_claims_rows` — just the claims rows
  - `synthetic_auth_rows` — just the auth rows
  - `facility_pool` — returns the `FacilityPool` instance
- [ ] Fixtures are session-scoped (generated once per test run)
- [ ] Fixtures work both in-memory and can be loaded into test Postgres via SQLAlchemy
- [ ] Typecheck passes, tests green

### US-SD-010: Create curated golden-file regression dataset
**Description:** As a test author, I want a small hand-crafted dataset with known expected outputs so that I can detect regressions in stitching, dedup, and reconciliation.

**Acceptance Criteria:**
- [ ] `tests/golden/input/` directory with static JSON files: `adt_events.json`, `claims.json`, `authorizations.json`
- [ ] `tests/golden/expected/` directory with expected output: `encounters.json`, `encounter_details.json`
- [ ] Covers exactly 10 patients with these specific scenarios: simple IP, ED-to-IP, transfer chain (2 facilities), readmission, cancelled admit, claims-only, ADT-only, orphan discharge, multi-source conflict, observation stay
- [ ] Each patient has a comment/description field explaining the scenario
- [ ] Expected output includes: encounter_id pattern, encounter_type, status, event count, confidence_score range, expected flags
- [ ] pytest test that loads golden input, runs through pipeline stages, and compares output to expected (using syrupy or direct comparison)
- [ ] Typecheck passes, tests green

### US-SD-011: Create test Postgres loader utility
**Description:** As a test author, I want a utility that loads synthetic data into a test Postgres database so that I can run integration tests against the full ingest pipeline.

**Acceptance Criteria:**
- [ ] `tests/utils/db_loader.py` with `load_synthetic_data(dataset: SyntheticDataset, connection_string: str)` function
- [ ] Creates tables `raw_adt_events`, `raw_claims`, `raw_authorizations` matching source config schemas
- [ ] Uses SQLAlchemy for portability
- [ ] Supports `teardown()` to drop test tables after test run
- [ ] Works with both local Postgres and any Postgres-compatible test database
- [ ] pytest fixture `test_db` that sets up and tears down automatically (skips if no Postgres available)
- [ ] Typecheck passes, tests green

### US-SD-012: Write integration tests using synthetic data
**Description:** As a test author, I want integration tests that run the ASRE pipeline end-to-end against synthetic data to validate correctness.

**Acceptance Criteria:**
- [ ] `tests/integration/test_pipeline_e2e.py` with at least these tests:
  - `test_simple_inpatient_encounter` — single patient, ADT + claims, verify stitched encounter
  - `test_ed_to_ip_merge` — ED arrival merges into IP encounter
  - `test_transfer_chain` — two linked encounters across facilities
  - `test_dedup_removes_duplicates` — duplicate events reduced to one
  - `test_claims_only_flagged` — encounter from claims only gets CLAIMS_ONLY_ENCOUNTER flag
  - `test_orphan_discharge_flagged` — orphan discharge gets ORPHAN_DISCHARGE flag
  - `test_dirty_records_handled` — malformed records don't crash pipeline, are logged
  - `test_confidence_scoring` — encounters get appropriate score ranges based on source mix
- [ ] Tests use the `synthetic_dataset` fixture or scenario builders
- [ ] Tests marked with `@pytest.mark.integration` for selective running
- [ ] All tests pass, typecheck passes

## Functional Requirements

- FR-1: All factories must accept a `seed` parameter for deterministic output (default: 42)
- FR-2: ADT factory must generate rows matching `raw_adt_events` schema exactly as defined in `customer_config/test_customer/sources/adt_vendor_x.yaml`
- FR-3: Claims factory must generate rows matching `raw_claims` schema exactly as defined in `customer_config/test_customer/sources/claims_clearinghouse.yaml`
- FR-4: Auth factory must generate rows matching `raw_authorizations` schema exactly as defined in `customer_config/test_customer/sources/auth_portal.yaml`
- FR-5: Facility names across all sources must reference the same `FacilityPool` so that cross-source matching can be tested
- FR-6: Dirty record generators must not modify the original record (return a copy)
- FR-7: The master dataset must be generatable in under 5 seconds on a modern laptop
- FR-8: All ICD-10 codes used must be real, valid codes (not made up)
- FR-9: All NPI numbers must follow the 10-digit Luhn check format
- FR-10: All DRG codes must be real MS-DRG codes
- FR-11: Temporal relationships must be realistic: admit before discharge, auth before or concurrent with admit, claims filed after discharge
- FR-12: Golden-file expected outputs must be updated whenever stitching/dedup/reconciliation logic changes (with explicit approval per CLAUDE.md)

## Non-Goals

- No dbt seed files (pytest-only for now)
- No Docker Compose setup for test Postgres (tests skip if no Postgres available)
- No performance/load testing dataset (200 patients is for correctness, not stress testing)
- No PHI or real patient data -- all data is synthetic with Faker
- No eligibility source factory (eligibility is not yet implemented in the pipeline)
- No UI or CLI for data generation -- Python API only

## Technical Considerations

- Use `Faker` library with medical providers (add `faker` to dev dependencies in `pyproject.toml`)
- Use `factory_boy` if it simplifies factory patterns, but plain classes are fine too
- All factories should be importable from `tests.factories` package
- Golden files stored as JSON for human readability and easy diffing
- Integration tests should use `@pytest.mark.integration` and be skippable via `pytest -m "not integration"`
- Test Postgres connection string should come from `TEST_DATABASE_URL` env var (default: `postgresql://localhost:5432/asre_test`)

## Success Metrics

- 200+ unique patient scenarios generated deterministically
- All existing 58+ unit tests continue to pass (no regressions)
- Golden-file regression tests catch any unintended changes to stitching/dedup/reconciliation output
- Integration tests validate end-to-end pipeline correctness
- Dirty record tests confirm error tolerance without crashes

## Open Questions

- Should we include an eligibility source factory now (ahead of pipeline support) or wait?
- Should golden-file comparison use syrupy snapshots or direct JSON comparison?
- What Postgres version should integration tests target?
