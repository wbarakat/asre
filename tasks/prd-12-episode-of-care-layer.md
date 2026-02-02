# PRD-12: Episode-of-Care Layer

## Introduction

Build the episode-of-care layer that groups related encounters — readmissions, post-acute transitions, planned returns, and ED bounce-backs — into longitudinal episodes representing a patient's full care journey. This runs as post-processing after encounters are materialized and can be recomputed independently.

**SPEC References:** §9 (episode-of-care layer — all subsections), §5.12-5.14 (episode stages), §4.2 (episode_stitching config)

## Goals

- Group related encounters into episodes using configurable linkage rules
- Classify episode types using a pluggable condition grouper (AHRQ CCS default)
- Compute episode-level confidence scores
- Support independent recomputation without re-running the full pipeline
- Populate episode_id FK on encounters

## Dependencies

- PRD-10 (materialized encounters in `admission_events_unified`)

## User Stories

### US-001: Implement episode stitching algorithm
**Description:** As a developer, I need to group encounters into episodes based on temporal and clinical linkage rules.

**Acceptance Criteria:**
- [ ] `asre/episode/episode_stitcher.py` defines `EpisodeStitcher` class
- [ ] Algorithm per SPEC §9.2:
  1. Query encounters per patient ordered by admit_ts
  2. For each encounter, check linkage rules against prior encounters
  3. Link to existing episode or create new
- [ ] Linkage rules (all windows configurable):
  - **Readmission:** Admit to any acute facility within `readmission_window_days` (default 30) of prior discharge
  - **Post-acute linkage:** Acute discharge → SNF/LTACH/rehab admit within `post_acute_linkage_days` (default 14)
  - **Planned return:** Scheduled return within `planned_return_days` (default 90)
  - **ED bounce-back:** ED visit within `ed_bounceback_days` (default 7) of prior discharge
- [ ] Unit tests for each linkage rule

### US-002: Implement readmission linkage
**Description:** As a developer, I need readmissions linked to the same episode as the index admission.

**Acceptance Criteria:**
- [ ] Acute admit within 30 days of prior acute discharge → same episode
- [ ] Both encounters must involve acute facilities
- [ ] Episode's `includes_readmission = true`
- [ ] Unit test: discharge Jan 1, readmit Jan 15 → same episode
- [ ] Unit test: discharge Jan 1, readmit Feb 15 → different episodes

### US-003: Implement post-acute linkage
**Description:** As a developer, I need acute → post-acute transitions linked into the same episode.

**Acceptance Criteria:**
- [ ] Acute discharge → SNF/LTACH/rehab admit within 14 days → same episode
- [ ] Episode's `includes_post_acute = true`
- [ ] Facility type checked via facility registry
- [ ] Unit test: acute discharge Jan 1, SNF admit Jan 5 → same episode
- [ ] Unit test: acute discharge Jan 1, SNF admit Jan 20 → different episodes

### US-004: Implement ED bounce-back linkage
**Description:** As a developer, I need ED visits shortly after discharge linked to the same episode.

**Acceptance Criteria:**
- [ ] ED visit within 7 days of prior discharge → same episode
- [ ] Unit test: discharge Jan 1, ED visit Jan 4 → same episode
- [ ] Unit test: discharge Jan 1, ED visit Jan 10 → different episodes

### US-005: Generate deterministic episode IDs
**Description:** As a developer, I need episode IDs that are stable across re-processing.

**Acceptance Criteria:**
- [ ] `episode_id` deterministically derived from the first encounter in the episode
- [ ] Same encounters always produce same episode_id
- [ ] Unit test: same encounter set → same episode_id on repeated runs

### US-006: Implement condition grouper interface
**Description:** As a developer, I need a pluggable interface for episode type classification.

**Acceptance Criteria:**
- [ ] `asre/groupers/base.py` defines `ConditionGrouper` ABC per SPEC §9.3:
  ```python
  class ConditionGrouper(ABC):
      @abstractmethod
      def group(self, diagnosis_codes: list[str], drg: str | None) -> str:
          """Return episode type classification."""
  ```
- [ ] Return values: surgical, medical, chronic_exacerbation, maternity, behavioral_health, unclassified
- [ ] Unit test: verify interface is abstract

### US-007: Implement AHRQ CCS grouper
**Description:** As a developer, I need the default condition grouper using AHRQ CCS ICD-10 classifications.

**Acceptance Criteria:**
- [ ] `asre/groupers/ahrq_ccs.py` implements `ConditionGrouper`
- [ ] Loads CCS crosswalk data (ICD-10-CM → CCS category mapping)
- [ ] Maps CCS categories to episode types:
  - Surgical CCS categories → "surgical"
  - Medical CCS categories → "medical"
  - Chronic disease categories → "chronic_exacerbation"
  - Maternity-related → "maternity"
  - Behavioral health → "behavioral_health"
  - Unrecognized → "unclassified"
- [ ] DRG-based rules checked first (surgical DRGs, maternity DRGs, etc.)
- [ ] `asre/episode/condition_grouper.py` dispatches: DRG rules first, then AHRQ CCS fallback
- [ ] Unit test: hip replacement DRG → surgical
- [ ] Unit test: pneumonia ICD-10 → medical
- [ ] Unit test: unknown code → unclassified

### US-008: Implement episode-level confidence scoring
**Description:** As a developer, I need episode confidence as a weighted mean of encounter scores.

**Acceptance Criteria:**
- [ ] `asre/episode/episode_scorer.py` defines `EpisodeScorer` class
- [ ] `episode_confidence = sum(encounter_confidence_i * los_hours_i) / sum(los_hours_i)` per SPEC §9.4
- [ ] Encounters with zero LOS (e.g., ED-only) use minimum weight of 1 hour
- [ ] Unit test: two encounters (score 0.8, LOS 48h) and (score 0.6, LOS 24h) → weighted mean
- [ ] Unit test: ED-only encounter with zero LOS uses 1 hour weight

### US-009: Populate episode metadata
**Description:** As a developer, I need episode output fields populated correctly.

**Acceptance Criteria:**
- [ ] All fields from SPEC §3.4 `asre_episodes` populated:
  - episode_id, patient_key, episode_type, episode_status
  - episode_start_ts (earliest admit_ts), episode_end_ts (latest discharge_ts or null)
  - total_los_days (cumulative LOS across all encounters)
  - encounter_ids (ordered list), encounter_count, facility_count
  - facility_sequence (ordered canonical IDs showing care pathway)
  - includes_readmission, includes_post_acute, is_acute
  - principal_diagnosis, diagnosis_codes (from primary encounter)
  - confidence_score, created_at, updated_at
- [ ] episode_status: active (any encounter open), closed (all closed), reopened
- [ ] Unit test: multi-encounter episode → all metadata correct

### US-010: Implement episode stages
**Description:** As a developer, I need episode stages that plug into the pipeline.

**Acceptance Criteria:**
- [ ] `EpisodeStitchStage`: stitches encounters into episodes
- [ ] `EpisodeMaterializeStage`: writes episodes to `asre_episodes`, updates `episode_id` FK on encounters
- [ ] `EpisodeQualityStage`: computes episode-level metrics (episode count, readmission rate, mean confidence)
- [ ] Stages integrate with pipeline runner as stages 10-12
- [ ] dbt model: `dbt_project/models/marts/asre_episodes.sql`
- [ ] dbt tests: unique on episode_id, relationships from admission_events_unified.episode_id
- [ ] Migration: `004_episode_tables.py` creates asre_episodes table

### US-011: Support independent episode recomputation
**Description:** As a developer, I need to recompute episodes without re-running the full pipeline.

**Acceptance Criteria:**
- [ ] `asre episodes --recompute` CLI command runs only episode stages (10-12)
- [ ] Reads from materialized `admission_events_unified` table
- [ ] Does NOT re-run ingest, canonicalize, stitch, dedup, reconcile, score stages
- [ ] Useful when episode rules change and need reprocessing

## Functional Requirements

- FR-01: Episode stitching is configurable (can be disabled via `episode_stitching.enabled: false`)
- FR-02: All linkage windows are configurable per customer
- FR-03: Condition grouper is pluggable — customers can provide custom implementations
- FR-04: Episode IDs are deterministic (same inputs → same IDs)
- FR-05: Episode stitching runs on materialized encounters (not in-memory pipeline state)
- FR-06: Encounters can belong to at most one episode
- FR-07: CCS crosswalk data bundled with ASRE (no external downloads at runtime)

## Non-Goals

- No ML-based episode classification (future per SPEC §18.2)
- No custom grouper implementations beyond AHRQ CCS (interface only — customers implement their own)
- No planned return detection (requires admission type metadata not available in v1)

## Technical Considerations

- AHRQ CCS crosswalk files are public domain — include in package data
- CCS data files need annual updates when new ICD-10 codes are released
- Episode stitching can be expensive for patients with many encounters — optimize per-patient queries
- Consider caching encounter queries per patient for efficiency

## TDD Approach

1. Write tests for each linkage rule (readmission, post-acute, ED bounce-back)
2. Write tests for episode ID determinism
3. Write tests for condition grouper (DRG-based and CCS-based)
4. Write tests for episode scoring
5. Write tests for episode metadata population
6. Write golden-file tests: known encounter sets → known episodes
7. Write integration test: full pipeline + episode stitching end-to-end
8. Implement to make tests pass

## Success Metrics

- Readmissions, post-acute transfers, and ED bounce-backs correctly grouped into episodes
- Episode type classification works for surgical, medical, maternity cases
- Episode confidence is correct weighted mean
- `asre episodes --recompute` works independently
- Golden-file tests pass for all episode scenarios
