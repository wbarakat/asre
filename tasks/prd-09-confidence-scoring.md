# PRD-09: Confidence Scoring

## Introduction

Build the confidence scoring engine that assigns a 0.0-1.0 reliability score to each encounter based on data completeness, source agreement, and quality flags. Scores drive downstream decisions about which encounters are trusted for analytics.

**SPEC References:** §6 (confidence scoring — all subsections), §4.2 (confidence_scoring config)

## Goals

- Compute weighted confidence score from binary signals
- Apply penalty flags that reduce score
- Detect stale open encounters using facility-type-aware thresholds
- Make all weights, penalties, and thresholds configurable

## Dependencies

- PRD-01 (models)
- PRD-02 (ConfidenceScoringConfig, stale encounter thresholds)
- PRD-08 (reconciled encounters with confidence_flags)

## User Stories

### US-001: Implement base score computation
**Description:** As a developer, I need a weighted sum of binary signals normalized to [0, 1].

**Acceptance Criteria:**
- [ ] `asre/score/confidence_scorer.py` defines `ConfidenceScorer` class
- [ ] Computes: `base_score = sum(signal_i * weight_i) / sum(weight_i)`
- [ ] 7 signals with default weights per SPEC §6.2:
  - HAS_CLAIMS (30): at least one claims event
  - HAS_ADT_ADMIT (20): ADT admit event present
  - HAS_ADT_DISCHARGE (10): ADT discharge event present
  - HAS_AUTH (10): auth signal matches
  - FACILITY_RESOLVED (5): facility matched to canonical ID
  - TIMESTAMPS_CONSISTENT (15): ADT and claims within tolerance
  - PATIENT_CLASS_CONSISTENT (10): ADT and claims agree on encounter type
- [ ] Maximum raw score = 100, normalized to 1.0
- [ ] Unit test: all signals present → score = 1.0
- [ ] Unit test: only HAS_CLAIMS → score = 30/100 = 0.30
- [ ] Unit test: HAS_CLAIMS + HAS_ADT_ADMIT → score = 50/100 = 0.50

### US-002: Implement penalty application
**Description:** As a developer, I need penalty flags to reduce the base score.

**Acceptance Criteria:**
- [ ] 9 penalties with default values per SPEC §6.3:
  - MISSING_DISCHARGE: -0.15
  - ORPHAN_DISCHARGE: -0.20
  - TIMESTAMP_MISMATCH: -0.10
  - CLAIMS_ONLY_ENCOUNTER: -0.10
  - STALE_OPEN_ENCOUNTER: -0.20
  - DUPLICATE_DETECTED: -0.05
  - FACILITY_UNRESOLVED: -0.10
  - AUTH_WITHOUT_ADMIT: -0.05
  - CANCELLED_AND_REOPENED: -0.05
- [ ] Penalties are subtracted from base score
- [ ] Final score floored at 0.0 (never negative)
- [ ] Unit test: base score 0.50 with MISSING_DISCHARGE → 0.35
- [ ] Unit test: base score 0.20 with ORPHAN_DISCHARGE(-0.20) + FACILITY_UNRESOLVED(-0.10) → 0.0 (floored)

### US-003: Populate confidence_flags array
**Description:** As a developer, I need the encounter to list all flags that affected its score.

**Acceptance Criteria:**
- [ ] `confidence_flags` contains names of all active signals AND all applied penalties
- [ ] Positive signals included when signal = 1 (e.g., "HAS_CLAIMS")
- [ ] Penalty flags included when penalty applied (e.g., "MISSING_DISCHARGE")
- [ ] Unit test: encounter with claims + missing discharge → flags include both "HAS_CLAIMS" and "MISSING_DISCHARGE"

### US-004: Implement stale encounter detection
**Description:** As a developer, I need facility-type-aware stale encounter thresholds.

**Acceptance Criteria:**
- [ ] `STALE_OPEN_ENCOUNTER` flag applied when encounter is open (no discharge) AND open duration exceeds facility-type threshold
- [ ] Default thresholds per SPEC §6.6:
  - acute: 30 days
  - ed_standalone: 3 days
  - ltach: 90 days
  - snf: 120 days
  - rehab: 60 days
  - psych: 90 days
  - default: 30 days
- [ ] Threshold selected based on facility's `facility_type` from registry
- [ ] If facility_type unknown, use `default` threshold
- [ ] Unit test: acute facility, open 31 days → STALE_OPEN_ENCOUNTER
- [ ] Unit test: SNF, open 100 days → no stale flag (threshold 120)
- [ ] Unit test: unknown facility type, open 31 days → STALE_OPEN_ENCOUNTER (default 30)

### US-005: Implement ScoreStage
**Description:** As a developer, I need the scoring stage to plug into the pipeline runner.

**Acceptance Criteria:**
- [ ] `asre/score/stage.py` defines `ScoreStage` implementing `PipelineStage`
- [ ] Processes list of encounters → returns scored encounters
- [ ] Records stage metrics: encounters_scored, avg_score, score_distribution (high/medium/low/very_low counts)
- [ ] Unit test: batch scoring with mixed-quality encounters

## Functional Requirements

- FR-01: All weights and penalties are configurable per customer via YAML (not hardcoded)
- FR-02: Custom signals/penalties can be added by the customer (arbitrary string→number mappings)
- FR-03: Score is a pure function of encounter state — no external dependencies
- FR-04: Score interpretation labels per SPEC §6.4: High (0.85-1.0), Medium (0.60-0.84), Low (0.30-0.59), Very Low (0.00-0.29)
- FR-05: TIMESTAMPS_CONSISTENT signal = 1 when either: both sources agree within tolerance, OR only one source has timestamps (no conflict)
- FR-06: PATIENT_CLASS_CONSISTENT signal = 1 when either: both sources agree on encounter_type, OR only one source has patient_class

## Non-Goals

- No ML-based scoring (future enhancement per SPEC §18.2)
- No manual score overrides
- No score history tracking (just current score)

## Technical Considerations

- Scoring is computationally trivial — pure arithmetic. Focus on correctness, not performance.
- Consider a `ScoreBreakdown` helper that shows the contribution of each signal and penalty (useful for debugging)
- Stale encounter detection requires current timestamp — inject via PipelineContext for testability

## TDD Approach

1. Write tests for base score with various signal combinations
2. Write tests for each penalty application
3. Write tests for score floor at 0.0
4. Write tests for stale detection with each facility type
5. Write tests for confidence_flags population
6. Write golden-file test: known encounters → known scores and flags
7. Implement to make tests pass

## Success Metrics

- Scoring formula matches SPEC §6.1 exactly
- All signal/penalty combinations produce expected scores
- Stale detection respects facility-type thresholds
- Golden-file tests pass for scoring scenarios
