# ASRE — Admission Signal Reliability Engine

## Technical Specification v1.1

**Status:** Draft
**Date:** 2026-02-01

---

## 1. Overview

ASRE is a backend engine deployed into customer environments that ingests raw ADT, claims, and authorization signals, and produces trusted outputs: `admission_events_unified` — a stitched, deduplicated, reconciled encounter table — and `asre_episodes` — a longitudinal episode-of-care table grouping related encounters across facilities and time.

ASRE does **not** run analytics, predict outcomes, automate billing, or replace EHRs. It is a data reliability layer.

**Patient identity assumption:** ASRE assumes patient identity is pre-resolved upstream. `patient_key` is a stable identifier provided by the customer from their MPI/EMPI system. ASRE does not perform patient matching.

### 1.1 Design Principles

- **Warehouse-native:** Outputs are materialized tables/views in the customer's warehouse (Snowflake, BigQuery, Redshift).
- **Batch-only:** Hourly or daily runs. All processing is batch; there is no streaming interface.
- **Single-tenant:** One deployment per customer, running in their VPC.
- **Config-driven:** Customer-specific mappings, thresholds, and rules are defined in YAML.
- **Idempotent:** Same inputs + same batch produce identical outputs. Dedup on ingest using `source_record_id`.
- **No PHI in transit to ASRE vendor:** All processing happens inside the customer environment.
- **No API in v1:** Output is warehouse tables queried via SQL. A lightweight REST API for health, config, and facility review is planned for v1.1 (see §18.1).

---

## 2. Architecture

### 2.1 High-Level Components

```
┌─────────────────────────────────────────────────────────────────────┐
│  Customer Environment (VPC)                                         │
│                                                                     │
│  ┌──────────────┐    ┌──────────────────────────────────────────┐   │
│  │ Source Tables │    │ ASRE Engine (Container)                  │   │
│  │              │    │                                          │   │
│  │ - ADT        │───▶│  1. Ingest Adapters (Python)             │   │
│  │ - Claims     │    │  2. Canonical Event Model (staging)      │   │
│  │ - Auth       │    │  3. Encounter Stitching                  │   │
│  │              │    │  4. Deduplication                        │   │
│  │              │    │  5. Cross-Source Reconciliation           │   │
│  └──────────────┘    │  6. Confidence Scoring                   │   │
│                      │  7. Facility Normalization                │   │
│                      │  8. Data Quality / Observability          │   │
│                      │  9. Episode-of-Care Stitching             │   │
│                      │                                          │   │
│                      └──────────────┬───────────────────────────┘   │
│                                     │                               │
│                      ┌──────────────▼───────────────────────────┐   │
│                      │ Customer Warehouse                       │   │
│                      │                                          │   │
│                      │  admission_events_unified (output)       │   │
│                      │  asre_encounters_detail (output)         │   │
│                      │  asre_episodes (output)                  │   │
│                      │  asre_quality_metrics (output)           │   │
│                      │  asre_facility_registry (output)         │   │
│                      │  asre_audit_log (output)                 │   │
│                      │  asre_run_metrics (output)               │   │
│                      └──────────────────────────────────────────┘   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Tech Stack

| Component | Technology |
|-----------|-----------|
| Core engine | Python 3.11+ |
| Transformation layer | dbt-core + warehouse-specific adapter |
| Orchestration | Customer scheduler (Airflow, dbt Cloud, cron) or built-in CLI |
| Configuration | YAML |
| Container runtime | Docker (AWS ECS / GCP Cloud Run compatible) |
| Warehouse targets | Snowflake, BigQuery, Redshift (all three supported from v1) |
| Facility matching | Python (rapidfuzz, recordlinkage) |
| Condition grouping | AHRQ CCS ICD-10 grouper (public domain) + pluggable interface |
| Data quality | dbt tests + custom Python checks |
| Alerting | Webhook (Slack, email, PagerDuty via webhook) |

### 2.3 Runtime Modes

| Mode | Trigger | Scope |
|------|---------|-------|
| `full` | Initial load or recovery | Processes all historical data |
| `incremental` | Scheduled (hourly/daily) | Processes new/changed records since last watermark |

### 2.4 Internal Processing Interface

All internal processing uses the `EventBatch` abstraction:

```python
@dataclass
class EventBatch:
    batch_id: str
    events: list[CanonicalEvent]
```

### 2.5 dbt Role

ASRE uses a hybrid Python + dbt architecture. Python handles all complex logic (stitching, matching, scoring, episode grouping). dbt handles:

- **Materialization** of staging → output tables (merge/upsert)
- **Cross-warehouse SQL compatibility** (Snowflake/BigQuery/Redshift adapters)
- **Schema tests** (unique, not_null, accepted_values, relationships)
- **Quality metric aggregation** queries

---

## 3. Data Model

### 3.1 Input Sources

| Feed | Standard | Typical Format |
|------|----------|---------------|
| ADT | HL7 v2 (A01-A45) | Warehouse table (pre-parsed) |
| Claims | X12 837I/837P | Warehouse table (pre-parsed) |
| Auth | X12 278 or flat file | Warehouse table |

**Note:** Eligibility (X12 270/271) is not consumed in v1. It is a candidate for future enhancement.

**Assumption:** Raw messages have already been parsed into tabular form by upstream systems (EHR vendors, clearinghouses, integration engines). ASRE reads from warehouse tables, not raw message streams.

### 3.2 Canonical Event Model

All inputs are mapped to a single canonical schema before processing.

#### `asre_canonical_events` (staging)

| Column | Type | Description |
|--------|------|-------------|
| `event_id` | STRING | ASRE-generated unique ID (UUID) |
| `patient_key` | STRING | Mapped patient identifier (from customer MPI/EMPI) |
| `event_type` | STRING | Normalized event code (see §3.3) |
| `event_ts` | TIMESTAMP | Event timestamp |
| `source_system` | STRING | Identifier for originating feed (e.g., `adt_vendor_x`, `claims_clearinghouse`) |
| `source_record_id` | STRING | Original record ID from source |
| `facility_raw` | STRING | Raw facility name/ID from source |
| `facility_canonical_id` | STRING | Resolved canonical facility ID (populated by normalization) |
| `admit_flag` | BOOLEAN | True if event represents an admission |
| `discharge_flag` | BOOLEAN | True if event represents a discharge |
| `auth_flag` | BOOLEAN | True if event is an auth signal |
| `patient_class` | STRING | Inpatient / outpatient / observation / ED / null |
| `drg` | STRING | DRG code (claims only, nullable) |
| `principal_diagnosis` | STRING | Principal ICD-10 diagnosis code (nullable) |
| `diagnosis_codes` | VARIANT/JSON | Array of `{code, type, sequence, poa}` objects (nullable) |
| `auth_status` | STRING | approved / denied / pending / null |
| `payer_id` | STRING | Payer identifier (nullable) |
| `ingested_at` | TIMESTAMP | When ASRE ingested this record |
| `batch_id` | STRING | Processing batch identifier |
| `_raw_payload` | VARIANT/JSON | Original source record (for audit) |

### 3.3 Normalized Event Types

ADT events are normalized to a controlled vocabulary:

| Code | Meaning | HL7 Triggers |
|------|---------|-------------|
| `ADMIT` | Admission | A01, A04 (with IP class) |
| `DISCHARGE` | Discharge | A03 |
| `TRANSFER_IN` | Transfer into facility | A02 (receiving) |
| `TRANSFER_OUT` | Transfer out of facility | A02 (sending) |
| `ED_ARRIVAL` | ED registration | A04 |
| `ED_DEPARTURE` | ED departure (without admission) | A03 (with ED class) |
| `OBS_START` | Observation start | A01 (with OBS class) |
| `OBS_END` | Observation end | A03 (with OBS class) |
| `OBS_TO_IP` | Observation converted to inpatient | A06 |
| `CANCEL_ADMIT` | Cancelled admission | A11 |
| `CANCEL_DISCHARGE` | Cancelled discharge | A13 |
| `CLAIM_ADMIT` | Admission signal from claims | 837I admit date |
| `CLAIM_DISCHARGE` | Discharge signal from claims | 837I discharge date |
| `AUTH_APPROVED` | Auth approval signal | 278 response |
| `AUTH_DENIED` | Auth denial signal | 278 response |
| `AUTH_REQUESTED` | Auth request signal | 278 request |

### 3.4 Output Tables

#### `admission_events_unified` (primary output)

| Column | Type | Description |
|--------|------|-------------|
| `encounter_id` | STRING | ASRE-generated stable encounter ID (see §5.6) |
| `patient_key` | STRING | Patient identifier |
| `encounter_type` | STRING | `inpatient`, `observation`, `ed_only`, `outpatient` |
| `status` | STRING | `open`, `closed`, `cancelled` |
| `admit_ts` | TIMESTAMP | Best-known admission timestamp |
| `discharge_ts` | TIMESTAMP | Best-known discharge timestamp (null if open) |
| `facility_canonical_id` | STRING | Resolved facility |
| `facility_name` | STRING | Display name |
| `is_acute` | BOOLEAN | Derived from `facility_type` in facility registry |
| `los_hours` | FLOAT | Length of stay in hours |
| `source_event_ids` | ARRAY[STRING] | All canonical event IDs that compose this encounter |
| `source_systems` | ARRAY[STRING] | Which feeds contributed |
| `has_adt` | BOOLEAN | ADT signal present |
| `has_claims` | BOOLEAN | Claims signal present |
| `has_auth` | BOOLEAN | Auth signal present |
| `confidence_score` | FLOAT | 0.0-1.0 (see §6) |
| `confidence_flags` | ARRAY[STRING] | Reasons affecting score (see §6.2) |
| `admit_source_priority` | STRING | Which source determined admit_ts |
| `discharge_source_priority` | STRING | Which source determined discharge_ts |
| `payer_id` | STRING | Primary payer |
| `drg` | STRING | DRG code (if available) |
| `principal_diagnosis` | STRING | Principal ICD-10 from claims |
| `admitting_diagnosis` | STRING | Admitting ICD-10 (nullable) |
| `diagnosis_codes` | ARRAY[OBJECT] | All diagnoses with role/sequence/POA indicator |
| `is_readmission` | BOOLEAN | Readmit to any acute facility within 30 days of prior discharge |
| `readmission_days` | INT | Days since prior discharge (nullable, populated only when `is_readmission` is true) |
| `obs_to_ip_conversion` | BOOLEAN | True if observation converted to inpatient |
| `transfer_chain` | ARRAY[STRING] | Ordered encounter_ids if part of transfer sequence |
| `episode_id` | STRING | FK to `asre_episodes` (nullable, populated by episode stitching) |
| `created_at` | TIMESTAMP | When encounter was first created |
| `updated_at` | TIMESTAMP | Last modified |
| `asre_version` | STRING | Engine version that produced this row |

#### `asre_encounters_detail` (event-level detail)

| Column | Type | Description |
|--------|------|-------------|
| `encounter_id` | STRING | FK to `admission_events_unified` |
| `event_id` | STRING | FK to canonical event |
| `event_type` | STRING | Normalized event type |
| `event_ts` | TIMESTAMP | Event timestamp |
| `source_system` | STRING | Originating feed |
| `role_in_encounter` | STRING | `admit_anchor`, `discharge_anchor`, `supporting`, `conflicting` |

#### `asre_episodes` (episode-of-care output)

| Column | Type | Description |
|--------|------|-------------|
| `episode_id` | STRING | Stable episode identifier |
| `patient_key` | STRING | Patient identifier |
| `episode_type` | STRING | `surgical`, `medical`, `chronic_exacerbation`, `maternity`, `behavioral_health`, `unclassified` |
| `episode_status` | STRING | `active`, `closed`, `reopened` |
| `episode_start_ts` | TIMESTAMP | Earliest admit_ts across all encounters |
| `episode_end_ts` | TIMESTAMP | Latest discharge_ts, or null if active |
| `total_los_days` | FLOAT | Cumulative LOS across all encounters |
| `encounter_ids` | ARRAY[STRING] | Ordered list of encounter IDs in this episode |
| `encounter_count` | INT | Number of encounters in the episode |
| `facility_count` | INT | Number of distinct facilities involved |
| `facility_sequence` | ARRAY[STRING] | Ordered facility canonical IDs (shows care pathway) |
| `includes_readmission` | BOOLEAN | True if episode contains a readmission |
| `includes_post_acute` | BOOLEAN | True if episode spans acute → post-acute |
| `is_acute` | BOOLEAN | True if any encounter in the episode is acute |
| `principal_diagnosis` | STRING | Principal ICD-10 from the primary encounter |
| `diagnosis_codes` | ARRAY[OBJECT] | Aggregated diagnoses across all encounters in episode |
| `confidence_score` | FLOAT | Episode-level confidence (aggregate of encounter scores) |
| `created_at` | TIMESTAMP | When episode was first created |
| `updated_at` | TIMESTAMP | Last modified |

#### `asre_facility_registry`

| Column | Type | Description |
|--------|------|-------------|
| `facility_canonical_id` | STRING | Stable ID |
| `facility_name` | STRING | Canonical display name |
| `npi` | STRING | NPI number (nullable) |
| `ccn` | STRING | CMS Certification Number (nullable) |
| `aliases` | ARRAY[STRING] | Known name variants |
| `address` | STRING | Facility address |
| `facility_type` | STRING | `acute`, `ltach`, `snf`, `rehab`, `psych`, `ed_standalone` |
| `last_updated` | TIMESTAMP | Last registry update |

#### `asre_quality_metrics`

| Column | Type | Description |
|--------|------|-------------|
| `metric_id` | STRING | Unique metric ID |
| `run_id` | STRING | Batch run identifier |
| `run_ts` | TIMESTAMP | When the run completed |
| `metric_name` | STRING | Metric identifier (see §8) |
| `metric_value` | FLOAT | Measured value |
| `threshold` | FLOAT | Configured threshold |
| `status` | STRING | `pass`, `warn`, `fail` |
| `detail` | VARIANT/JSON | Supporting context |

#### `asre_audit_log`

| Column | Type | Description |
|--------|------|-------------|
| `log_id` | STRING | Unique log entry ID |
| `run_id` | STRING | Batch run identifier |
| `timestamp` | TIMESTAMP | When the action occurred |
| `action` | STRING | `ingest`, `stitch`, `dedup`, `reconcile`, `score`, `normalize`, `episode_stitch` |
| `entity_type` | STRING | `event`, `encounter`, `facility`, `episode` |
| `entity_id` | STRING | Affected entity ID |
| `detail` | VARIANT/JSON | What changed and why |

#### `asre_run_metrics` (pipeline observability)

| Column | Type | Description |
|--------|------|-------------|
| `run_id` | STRING | Batch run ID |
| `stage_name` | STRING | Pipeline stage name |
| `started_at` | TIMESTAMP | Stage start time |
| `completed_at` | TIMESTAMP | Stage end time |
| `records_in` | INT | Records entering stage |
| `records_out` | INT | Records exiting stage |
| `errors` | INT | Failed records in stage |
| `status` | STRING | `success`, `failed`, `skipped` |

---

## 4. Customer Mapping Layer

### 4.1 Mapping Config Format

Each customer provides a YAML mapping file per source feed.

#### Example: ADT Feed

```yaml
# customer_config/acme_health/sources/adt_vendor_x.yaml

source:
  name: "adt_vendor_x"
  type: "adt"
  table: "raw.adt_messages"
  incremental_key: "msg_timestamp"  # column used for watermarking

field_mappings:
  patient_key: "member_id"
  event_ts: "msg_timestamp"
  event_type: "hl7_event"
  facility_raw: "hospital_name"
  source_record_id: "message_control_id"
  patient_class: "patient_class_code"
  payer_id: "insurance_plan_id"

event_type_rules:
  admit_flag: "hl7_event IN ('A01') AND patient_class_code IN ('I', 'IP')"
  discharge_flag: "hl7_event == 'A03'"
  event_type_map:
    "A01":
      default: "ADMIT"
      when:
        - condition: "patient_class_code IN ('O', 'OBS')"
          then: "OBS_START"
        - condition: "patient_class_code IN ('E', 'ED')"
          then: "ED_ARRIVAL"
    "A03":
      default: "DISCHARGE"
      when:
        - condition: "patient_class_code IN ('E', 'ED')"
          then: "ED_DEPARTURE"
        - condition: "patient_class_code IN ('O', 'OBS')"
          then: "OBS_END"
    "A02": "TRANSFER_IN"
    "A06": "OBS_TO_IP"
    "A11": "CANCEL_ADMIT"
    "A13": "CANCEL_DISCHARGE"

filters:
  exclude: "hl7_event IN ('A08', 'A31')"  # demographic updates, not admission signals
```

#### Example: Claims Feed

```yaml
# customer_config/acme_health/sources/claims_clearinghouse.yaml

source:
  name: "claims_clearinghouse"
  type: "claims"
  table: "raw.institutional_claims"
  incremental_key: "claim_received_date"

field_mappings:
  patient_key: "subscriber_id"
  facility_raw: "billing_provider_name"
  source_record_id: "claim_id"
  payer_id: "payer_code"
  drg: "drg_code"
  principal_diagnosis: "principal_dx_code"
  admitting_diagnosis: "admitting_dx_code"
  diagnosis_codes: "all_dx_codes"  # JSON array or specify parsing rules

# Claims produce paired admit/discharge events from a single row
paired_events:
  admit:
    event_ts: "admission_date"
    event_type: "CLAIM_ADMIT"
    admit_flag: true
  discharge:
    event_ts: "discharge_date"
    event_type: "CLAIM_DISCHARGE"
    discharge_flag: true

patient_class_rules:
  - condition: "bill_type_code LIKE '11%'"
    then: "inpatient"
  - condition: "bill_type_code LIKE '13%'"
    then: "outpatient"
  - condition: "bill_type_code LIKE '12%'"
    then: "inpatient"  # hospital swing bed
```

#### Example: Auth Feed

```yaml
# customer_config/acme_health/sources/auth_portal.yaml

source:
  name: "auth_portal"
  type: "auth"
  table: "raw.authorization_records"
  incremental_key: "updated_at"

field_mappings:
  patient_key: "member_number"
  event_ts: "auth_decision_date"
  facility_raw: "servicing_facility"
  source_record_id: "auth_number"
  payer_id: "plan_code"

auth_status_map:
  "A": "approved"
  "D": "denied"
  "P": "pending"
  "M": "modified"

event_type_rules:
  event_type_map:
    "approved": "AUTH_APPROVED"
    "denied": "AUTH_DENIED"
    "pending": "AUTH_REQUESTED"
```

### 4.2 Global Customer Config

```yaml
# customer_config/acme_health/config.yaml

customer:
  name: "Acme Health"
  id: "acme_health"

warehouse:
  type: "snowflake"  # snowflake | bigquery | redshift
  schema_prefix: "asre"

schedule:
  mode: "incremental"
  frequency: "hourly"
  lookback_buffer:
    adt: "2h"         # ADT arrives near real-time; small lookback
    claims: "45d"     # Claims lag by weeks; large lookback
    auth: "7d"        # Auth updates trickle over days
    default: "2h"     # Fallback for any unspecified source type

encounter_stitching:
  time_window_hours: 48        # max gap between events in same encounter
  facility_must_match: true     # events must share facility to stitch
  same_timestamp_tiebreaker:    # when events share identical event_ts
    - claims                    # highest priority (adjudicated)
    - adt                       # second priority (real-time)
    - auth                      # lowest priority
  patient_class_transitions:
    - from: "observation"
      to: "inpatient"
      action: "merge"           # merge into single encounter
    - from: "ed"
      to: "inpatient"
      action: "merge"
    - from: "inpatient"
      to: "inpatient"
      action: "new_encounter"   # same-day readmit = new encounter

deduplication:
  time_tolerance_minutes: 30   # events within window = potential duplicates
  match_fields: ["patient_key", "event_type", "facility_canonical_id"]

reconciliation:
  timestamp_priority:            # per-field priority; higher = more trusted
    adt: 100                     # ADT is closest to real-time event
    claims: 80
    auth: 40
  classification_priority:       # for encounter_type, DRG, payer, diagnosis
    claims: 100                  # claims is adjudicated billing record
    adt: 80
    auth: 40
  timestamp_tolerance_hours: 24  # ADT and claims timestamps can differ by this amount

episode_stitching:
  enabled: true
  rules:
    readmission_window_days: 30       # readmit to any facility within N days
    post_acute_linkage_days: 14       # acute discharge → SNF/LTACH/rehab admit
    planned_return_days: 90           # scheduled return (chemo, staged surgery)
    ed_bounceback_days: 7             # ED visit within N days of discharge
  condition_grouper: "ahrq_ccs"       # default grouper; pluggable
  episode_confidence:
    method: "weighted_mean"           # aggregate encounter scores

facility_normalization:
  fuzzy_threshold: 0.85        # rapidfuzz score threshold
  alias_file: "facility_aliases.yaml"
  use_npi_registry: true
  use_ccn_registry: true

confidence_scoring:
  weights:
    HAS_CLAIMS: 30
    HAS_ADT_ADMIT: 20
    HAS_ADT_DISCHARGE: 10
    HAS_AUTH: 10
    FACILITY_RESOLVED: 5
    TIMESTAMPS_CONSISTENT: 15
    PATIENT_CLASS_CONSISTENT: 10
  penalties:
    MISSING_DISCHARGE: 0.15
    ORPHAN_DISCHARGE: 0.20
    TIMESTAMP_MISMATCH: 0.10
    CLAIMS_ONLY_ENCOUNTER: 0.10
    STALE_OPEN_ENCOUNTER: 0.20
    DUPLICATE_DETECTED: 0.05
    FACILITY_UNRESOLVED: 0.10
    AUTH_WITHOUT_ADMIT: 0.05
    CANCELLED_AND_REOPENED: 0.05

alerting:
  enabled: true
  channels:
    - type: "webhook"
      url: "${ASRE_ALERT_WEBHOOK_URL}"
  thresholds:
    duplicate_rate_warn: 0.05
    duplicate_rate_fail: 0.15
    missing_discharge_rate_warn: 0.10
    missing_discharge_rate_fail: 0.25
    reconciliation_mismatch_rate_warn: 0.10
    reconciliation_mismatch_rate_fail: 0.20
    low_confidence_rate_warn: 0.15
    low_confidence_rate_fail: 0.30
    failed_event_rate_warn: 0.01
    failed_event_rate_fail: 0.05
```

---

## 5. Core Processing Pipeline

### 5.1 Pipeline Stages

Each batch run executes these stages in order:

```
Ingest → Canonicalize → Facility Normalize → Stitch → Dedup → Reconcile → Score → Materialize → Quality Check → Episode Stitch → Episode Materialize → Episode Quality Check
```

The first nine stages (Ingest through Quality Check) produce encounter-level outputs. The final three stages run as post-processing to produce episode-level outputs. Episode stages can be disabled via config (`episode_stitching.enabled: false`).

### 5.2 Stage 1: Ingest

**Input:** Source tables as defined in customer mapping configs.
**Output:** Raw records pulled into staging.

- Read from each configured source table.
- For incremental mode: filter by `incremental_key > last_watermark - lookback_buffer`. Each source type uses its own lookback window (e.g., claims uses 45d, ADT uses 2h).
- Apply `filters.exclude` rules.
- Dedup on ingest using `source_record_id` to ensure idempotency.
- Persist `_raw_payload` for audit.

### 5.3 Stage 2: Canonicalize

**Input:** Raw staged records.
**Output:** `asre_canonical_events` rows.

- Apply `field_mappings` to map source columns to canonical schema.
- Apply `event_type_rules` to derive `event_type`, `admit_flag`, `discharge_flag`.
- For paired event sources (claims): emit two canonical events per source row.
- Map diagnosis fields (`principal_diagnosis`, `diagnosis_codes`) for claims sources.
- Generate `event_id` (UUID).
- Set `ingested_at` and `batch_id`.

### 5.4 Stage 3: Facility Normalization

**Input:** Canonical events with `facility_raw` populated.
**Output:** `facility_canonical_id` populated on events; `asre_facility_registry` updated.

Processing steps:

1. **String normalization:** Uppercase, strip punctuation, expand abbreviations, normalize whitespace. Directional and campus tokens (East, West, North, South, Main, Downtown, Campus) are **preserved** — they distinguish distinct facilities (see §7).
2. **Exact match:** Check against `asre_facility_registry.aliases`.
3. **Fuzzy match:** If no exact match, score against known facilities using token-sort ratio. Accept if >= `fuzzy_threshold`.
4. **NPI/CCN lookup:** If source includes NPI or CCN, match directly against public registries.
5. **New facility:** If no match found, create a new facility record and flag for human review.

### 5.5 Stage 4: Encounter Stitching

**Input:** Canonical events (facility-normalized).
**Output:** `encounter_id` assigned to each event.

Algorithm:

1. Partition events by `patient_key`.
2. Sort by `event_ts` ascending. **Tiebreaker:** when events share identical `event_ts`, order by source type priority: claims > ADT > auth (configurable via `same_timestamp_tiebreaker`).
3. Initialize first event as a new encounter.
4. For each subsequent event:
   - If `event_ts` is within `time_window_hours` of the current encounter's last event AND facility matches (if `facility_must_match`):
     - Check `patient_class_transitions` rules.
     - If transition action is `merge`: add to current encounter.
     - If transition action is `new_encounter`: close current, start new.
   - If outside time window or facility mismatch: close current encounter, start new.
5. Handle cancellation events (`CANCEL_ADMIT`, `CANCEL_DISCHARGE`):
   - Find the most recent matching event in the current encounter.
   - Mark encounter status as `cancelled` (for cancel-admit) or reopen (for cancel-discharge).

### 5.6 Encounter ID Stability

`encounter_id` is deterministically derived from the first admit event:

```
encounter_id = hash(patient_key + facility_canonical_id + first_admit_source_record_id)
```

This ensures `encounter_id` is stable across re-processing runs. The same patient, facility, and originating source record always produce the same encounter ID, regardless of when or how many times the pipeline runs.

Edge cases:

- **ED → IP in same facility:** Merge into single encounter (type = `inpatient`).
- **OBS → IP conversion:** Merge; set `obs_to_ip_conversion = true`.
- **Transfer chain (Facility A → B → C):** Each facility segment is its own encounter. Link via `transfer_chain` array. Detection: discharge from Facility A within `time_window_hours` of admit at Facility B.
- **Overlapping encounters at different facilities:** Allowed (patient can be discharged from A and admitted to B on the same day).
- **No discharge event:** Encounter remains `status = open`. If open longer than the facility-type stale threshold (see §6.6), flag as `STALE_OPEN_ENCOUNTER`.

### 5.7 Stage 5: Deduplication

**Input:** Stitched encounters with assigned events.
**Output:** Deduplicated event set.

Rules:

1. Within each encounter, identify events that match on all `match_fields` within `time_tolerance_minutes`.
2. When duplicates found:
   - Keep the event with the highest source priority (per `reconciliation.timestamp_priority`).
   - If same source: keep the earliest ingested record.
   - Mark duplicates with `role_in_encounter = 'duplicate'` in the detail table (retained for audit).
3. Encounter-level dedup: if two encounters for the same patient have overlapping time windows at the same facility, merge them.

### 5.8 Stage 6: Cross-Source Reconciliation

**Input:** Deduplicated encounters.
**Output:** Reconciled encounters with `admit_source_priority` and `discharge_source_priority` set.

Reconciliation resolves conflicting signals across ADT, claims, and auth using context-dependent source priority:

1. **Timestamp selection:** Use `timestamp_priority` to determine which source provides `admit_ts` and `discharge_ts`. ADT is typically primary for timestamps (real-time, closest to actual event). If ADT and claims timestamps differ by more than `timestamp_tolerance_hours`, flag as `TIMESTAMP_MISMATCH`.

2. **Encounter type resolution:** Use `classification_priority` to determine `encounter_type`, `DRG`, `payer_id`, and diagnosis codes. Claims is typically primary for these fields (adjudicated billing record).

3. **Auth reconciliation:**
   - Auth is never used as the anchor for encounter creation.
   - Auth priority is lowest for both timestamps and classification — it serves a validation-only role.
   - If auth exists with no matching ADT/claims encounter: flag as `AUTH_WITHOUT_ADMIT`.
   - If encounter exists with matching auth: boost confidence.

4. **Missing event detection:**
   - Admit without discharge (and outside time window): flag `MISSING_DISCHARGE`.
   - Discharge without admit: flag `ORPHAN_DISCHARGE`.
   - Claims encounter with no ADT: flag `CLAIMS_ONLY_ENCOUNTER`.
   - ADT encounter with no claims (beyond expected lag): flag `ADT_ONLY_ENCOUNTER`.

### 5.9 Stage 7: Confidence Scoring

See §6 for full scoring specification.

### 5.10 Stage 8: Materialize

- Write/merge results into output tables (`admission_events_unified`, etc.).
- For incremental runs: use merge/upsert on `encounter_id`.
- Update `updated_at` timestamp.
- Compute `is_readmission` and `readmission_days` by comparing each encounter's admit_ts against prior discharges from acute facilities for the same patient within 30 days.
- Write `asre_audit_log` entries.

### 5.11 Stage 9: Quality Check

- Run all dbt tests and custom quality checks (see §8).
- Compute metrics and write to `asre_quality_metrics`.
- Evaluate thresholds; fire alerts if breached.
- Update watermark for next incremental run.

### 5.12 Stage 10: Episode Stitch

**Input:** Materialized encounters from `admission_events_unified`.
**Output:** `asre_episodes` rows; `episode_id` FK populated on encounters.

Episode stitching runs as post-processing after encounters are materialized. See §9 for the full episode stitching specification.

### 5.13 Stage 11: Episode Materialize

- Write/merge episode results into `asre_episodes`.
- Update `episode_id` FK on `admission_events_unified`.
- Write audit log entries for episode creation/modification.

### 5.14 Stage 12: Episode Quality Check

- Compute episode-level quality metrics (episode count, readmission rate, mean episode confidence).
- Evaluate episode-specific thresholds.
- Fire alerts if breached.

---

## 6. Confidence Scoring

### 6.1 Scoring Model

Each encounter receives a `confidence_score` between 0.0 and 1.0, computed as a weighted sum of binary signals normalized to [0, 1].

```
confidence_score = sum(signal_i * weight_i) / sum(weight_i)
```

### 6.2 Signals and Weights

| Signal | Weight | Condition for signal = 1 |
|--------|--------|-------------------------|
| `HAS_CLAIMS` | 30 | At least one claims event matches |
| `HAS_ADT_ADMIT` | 20 | ADT admit event present |
| `HAS_ADT_DISCHARGE` | 10 | ADT discharge event present |
| `HAS_AUTH` | 10 | Auth signal matches encounter |
| `FACILITY_RESOLVED` | 5 | Facility matched to canonical ID (not a new/unresolved facility) |
| `TIMESTAMPS_CONSISTENT` | 15 | ADT and claims timestamps within `timestamp_tolerance_hours` |
| `PATIENT_CLASS_CONSISTENT` | 10 | ADT and claims agree on encounter type |

**Maximum raw score:** 100 → normalized to 1.0.

### 6.3 Penalty Flags

Penalties are applied after the base score. Each penalty subtracts from the normalized score (floor at 0.0).

| Flag | Penalty | Trigger |
|------|---------|---------|
| `MISSING_DISCHARGE` | -0.15 | No discharge event and encounter open > 48h |
| `ORPHAN_DISCHARGE` | -0.20 | Discharge without matching admit |
| `TIMESTAMP_MISMATCH` | -0.10 | ADT vs claims admit time differs > tolerance |
| `CLAIMS_ONLY_ENCOUNTER` | -0.10 | No ADT signals at all |
| `STALE_OPEN_ENCOUNTER` | -0.20 | Open beyond facility-type threshold with no activity (see §6.6) |
| `DUPLICATE_DETECTED` | -0.05 | Duplicates found and resolved |
| `FACILITY_UNRESOLVED` | -0.10 | Facility could not be matched |
| `AUTH_WITHOUT_ADMIT` | -0.05 | Auth exists but no encounter match |
| `CANCELLED_AND_REOPENED` | -0.05 | Cancel event followed by re-admit |

### 6.4 Score Interpretation

| Range | Label | Recommended Action |
|-------|-------|-------------------|
| 0.85-1.00 | High | Trusted for downstream use |
| 0.60-0.84 | Medium | Usable; review flagged issues |
| 0.30-0.59 | Low | Manual review recommended |
| 0.00-0.29 | Very Low | Do not use without investigation |

### 6.5 Configurability

All weights, penalties, and thresholds are defined in the customer config YAML and can be tuned per deployment (see §4.2).

### 6.6 Stale Encounter Thresholds by Facility Type

Patients at long-stay facilities (LTACHs, SNFs, psych, rehab) can legitimately remain admitted for weeks or months. A single global threshold produces false positives. Stale encounter detection uses facility-type-aware thresholds:

| Facility Type | Default Stale Threshold | Rationale |
|---------------|------------------------|-----------|
| `acute` | 30 days | Most acute stays are < 14 days |
| `ed_standalone` | 3 days | ED visits rarely exceed hours |
| `ltach` | 90 days | LTACH stays average 25-30 days, can exceed 60 |
| `snf` | 120 days | SNF stays can be 20-100+ days |
| `rehab` | 60 days | Inpatient rehab typically 14-30 days |
| `psych` | 90 days | Psych stays vary widely |

Configured in customer YAML:

```yaml
encounter_stitching:
  stale_encounter_thresholds:
    acute: 30
    ed_standalone: 3
    ltach: 90
    snf: 120
    rehab: 60
    psych: 90
    default: 30  # fallback for untyped facilities
```

If `facility_type` is unknown or unresolved, the `default` threshold applies.

---

## 7. Facility Normalization

### 7.1 String Normalization Pipeline

The normalization pipeline preserves directional and campus tokens, which distinguish distinct facilities:

```
Input:  "St. Mary's Med Ctr - East Campus"
  → uppercase:        "ST. MARY'S MED CTR - EAST CAMPUS"
  → strip punctuation: "ST MARYS MED CTR EAST CAMPUS"
  → expand abbrevs:    "ST MARYS MEDICAL CENTER EAST CAMPUS"
  → remove suffixes:   "ST MARYS EAST CAMPUS"
  → normalize ws:      "ST MARYS EAST CAMPUS"
```

**Important:** Directional tokens (`EAST`, `WEST`, `NORTH`, `SOUTH`) and campus tokens (`MAIN`, `DOWNTOWN`, `CAMPUS`, `MIDTOWN`, `UPTOWN`) are **not** stripped during suffix removal. These tokens distinguish physically separate facilities or campuses (e.g., "St. Mary's East" and "St. Mary's West" are different locations). Only generic organizational suffixes (`HOSPITAL`, `MEDICAL CENTER`, `HEALTH SYSTEM`) are removed.

### 7.2 Abbreviation Dictionary

| Abbreviation | Expansion |
|-------------|-----------|
| MED CTR | MEDICAL CENTER |
| HOSP | HOSPITAL |
| REG | REGIONAL |
| MEM | MEMORIAL |
| UNIV | UNIVERSITY |
| GEN | GENERAL |
| COMM | COMMUNITY |
| CTR | CENTER |
| HLTH | HEALTH |
| SYS | SYSTEM |

Configurable per customer via YAML.

### 7.3 Matching Cascade

1. Exact match on normalized string → canonical ID
2. Exact match on NPI/CCN → canonical ID
3. Fuzzy match (token sort ratio >= threshold) → canonical ID (log match score)
4. No match → create new facility, flag `FACILITY_NEW_UNREVIEWED`

### 7.4 Public Registry Integration

- **NPI Registry:** NPPES (downloaded flat file, refreshed monthly).
- **CCN Registry:** CMS Provider of Services file.
- **HIFLD:** Homeland Infrastructure Foundation-Level Data (hospital locations).

These are loaded into `asre_facility_registry` during setup and refreshed on a configurable schedule.

Alias dictionary (`facility_aliases.yaml`):

```yaml
facilities:
  - canonical_id: "FAC_001"
    canonical_name: "St. Mary's Medical Center"
    npi: "1234567890"
    ccn: "050001"
    aliases:
      - "ST MARY HOSP"
      - "ST MARYS MEDICAL CTR"
      - "SAINT MARY HOSPITAL"
      - "ST. MARY'S MED CENTER"
```

---

## 8. Data Quality & Observability

### 8.1 dbt Tests

Built-in dbt tests run after every pipeline execution:

| Test | Table | Type |
|------|-------|------|
| `unique` | `admission_events_unified.encounter_id` | Schema |
| `not_null` | `admission_events_unified.patient_key` | Schema |
| `not_null` | `admission_events_unified.admit_ts` | Schema |
| `accepted_values` | `admission_events_unified.status` → `[open, closed, cancelled]` | Schema |
| `accepted_values` | `admission_events_unified.encounter_type` → `[inpatient, observation, ed_only, outpatient]` | Schema |
| `relationships` | `asre_encounters_detail.encounter_id` → `admission_events_unified.encounter_id` | Schema |
| `unique` | `asre_episodes.episode_id` | Schema |
| `relationships` | `admission_events_unified.episode_id` → `asre_episodes.episode_id` | Schema |

### 8.2 Custom Quality Metrics

Computed per run and stored in `asre_quality_metrics`:

| Metric | Computation |
|--------|------------|
| `duplicate_rate` | (duplicates found) / (total events ingested) |
| `missing_discharge_rate` | (open encounters > 48h) / (total encounters) |
| `reconciliation_mismatch_rate` | (encounters with TIMESTAMP_MISMATCH flag) / (encounters with multiple sources) |
| `low_confidence_rate` | (encounters with score < 0.60) / (total encounters) |
| `facility_unresolved_rate` | (events with unresolved facility) / (total events) |
| `auth_without_admit_rate` | (auth signals with no matching encounter) / (total auth signals) |
| `claims_only_rate` | (encounters from claims only) / (total encounters) |
| `avg_confidence_score` | Mean confidence score across all encounters |
| `events_ingested` | Count of events processed in this run |
| `encounters_created` | New encounters in this run |
| `encounters_updated` | Modified encounters in this run |
| `failed_event_rate` | (events that failed processing) / (total events ingested) |

### 8.3 Alerting

Alert evaluation runs after quality metrics are computed.

```yaml
alerting:
  channels:
    - type: "webhook"
      url: "${ASRE_ALERT_WEBHOOK_URL}"
      # Webhook payload is a JSON POST:
      # {
      #   "run_id": "...",
      #   "run_ts": "...",
      #   "alerts": [
      #     {"metric": "duplicate_rate", "value": 0.18, "threshold": 0.15, "severity": "fail"}
      #   ]
      # }
```

Severity is determined by matching against `warn` and `fail` thresholds in config.

---

## 9. Episode-of-Care Layer

### 9.1 Overview

The episode-of-care layer groups related encounters — including readmissions, post-acute transitions, and planned returns — into a single longitudinal episode representing the patient's full care journey for a given condition or event.

Episode stitching runs as post-processing after encounters are materialized (stages 10-12 in §5.1). This means episodes can be recomputed independently without re-running the full encounter pipeline.

### 9.2 Episode Stitching Algorithm

1. Query all encounters for a patient, ordered by `admit_ts`.
2. For each encounter, check linkage rules against prior encounters:
   - **Readmission:** Admit to any acute facility within `readmission_window_days` of a prior discharge.
   - **Post-acute linkage:** Discharge from acute facility → admit to SNF/LTACH/rehab within `post_acute_linkage_days`.
   - **Planned return:** Scheduled return (e.g., chemo cycle, staged surgery) within `planned_return_days`.
   - **ED bounce-back:** ED visit within `ed_bounceback_days` of a prior discharge.
3. If any rule matches, link to the existing episode. Otherwise, create a new episode.
4. All windows are configurable per customer and per episode type.

### 9.3 Episode Type Classification

Episode type is derived from the primary encounter (typically the first acute encounter) using a two-tier approach:

1. **DRG-based rules:** Map DRG codes to episode types (surgical, medical, maternity, etc.). Configurable rule set.
2. **AHRQ CCS ICD-10 grouper:** Use the AHRQ Clinical Classifications Software (CCS) for ICD-10-CM/PCS to group diagnosis codes into clinically meaningful categories. The AHRQ CCS is free and public domain.

The condition grouper is pluggable via a base interface:

```python
class ConditionGrouper(ABC):
    @abstractmethod
    def group(self, diagnosis_codes: list[str], drg: str | None) -> str:
        """Return episode type classification."""
        ...
```

The default implementation uses AHRQ CCS. Custom groupers (e.g., CMS Bundled Payment models, Prometheus) can be provided by implementing the interface.

### 9.4 Episode-Level Confidence Scoring

Episode confidence is computed as a weighted mean of encounter confidence scores, where weight is proportional to encounter LOS:

```
episode_confidence = sum(encounter_confidence_i * los_hours_i) / sum(los_hours_i)
```

For encounters with no LOS (e.g., ED-only), a minimum weight of 1 hour is used.

### 9.5 Why Episodes Matter

Without episodes, downstream teams must build their own logic to answer questions like: "Was this SNF admission part of the same care journey as the hip replacement last week?" or "Is this ED visit a bounce-back from the discharge 3 days ago?" Every organization rebuilds this. ASRE's positioning as the reliability layer is incomplete without it — encounter-level trust is necessary but not sufficient. Episode-level trust is the full promise.

---

## 10. Pipeline Observability

### 10.1 Structured Logging

All pipeline logs are emitted as structured JSON with stage context:

```json
{
  "timestamp": "2026-02-01T10:30:00Z",
  "level": "INFO",
  "stage": "stitch",
  "run_id": "run_20260201_1030",
  "message": "Encounter stitching complete",
  "records_in": 15000,
  "records_out": 4200,
  "duration_seconds": 12.4
}
```

### 10.2 Per-Stage Metrics

Each pipeline stage records timing and throughput metrics to `asre_run_metrics` (see §3.4 for schema). Metrics include:

- **Duration:** Wall-clock time per stage.
- **Throughput:** Records/second (records_out / duration).
- **Error count:** Events that failed processing in each stage.
- **Status:** `success`, `failed`, or `skipped`.

### 10.3 Run Summary

After each run, a summary is available via CLI (`asre inspect run <run_id>`) or by querying `asre_run_metrics` directly:

```sql
SELECT stage_name, records_in, records_out, errors,
       DATEDIFF('second', started_at, completed_at) AS duration_sec,
       status
FROM asre_run_metrics
WHERE run_id = 'run_20260201_1030'
ORDER BY started_at;
```

---

## 11. Error Handling & Recovery

### 11.1 Stage Checkpointing

Each pipeline stage commits its intermediate results before the next stage begins. If the pipeline fails mid-run:

- Completed stages are not re-executed.
- The pipeline resumes from the last successful stage.
- Resume is triggered via `asre run --resume <run_id>`.

### 11.2 Event-Level Error Tolerance

Individual events can fail processing (e.g., unparseable field, missing required column) without blocking the pipeline. Failed events are:

- Logged to `asre_audit_log` with action `error` and full error detail.
- Excluded from downstream stages for that run.
- Tracked in `asre_run_metrics` via the `errors` column.
- Tracked in `asre_quality_metrics` via the `failed_event_rate` metric.

If the failed event rate exceeds the configured threshold (`failed_event_rate_fail`), the pipeline halts and fires an alert.

### 11.3 Idempotency

The pipeline is fully idempotent: the same inputs + same batch produce identical outputs. This is achieved through:

- **Ingest dedup:** `source_record_id` is used to deduplicate on ingest. Re-ingesting the same source records produces no new canonical events.
- **Deterministic encounter IDs:** `encounter_id` is derived from `hash(patient_key + facility_canonical_id + first_admit_source_record_id)`, not from auto-increment or random UUID.
- **Deterministic episode IDs:** `episode_id` follows the same pattern, anchored on the first encounter in the episode.
- **Merge/upsert on materialize:** Output tables use merge operations keyed on `encounter_id` and `episode_id`.

---

## 12. Schema Migration

### 12.1 Version Tracking

ASRE tracks its schema version in an `asre_metadata` table:

| Column | Type | Description |
|--------|------|-------------|
| `key` | STRING | Metadata key |
| `value` | STRING | Metadata value |
| `updated_at` | TIMESTAMP | Last update |

The `schema_version` key stores the current schema version (e.g., `1.0.0`, `1.1.0`).

### 12.2 Auto-Migration

On startup, ASRE:

1. Reads `schema_version` from `asre_metadata`.
2. Compares against the expected version for the running engine.
3. If behind, runs pending migration scripts in order.
4. Updates `schema_version` after successful migration.

If `asre_metadata` does not exist (fresh install), ASRE runs the full initial schema creation.

### 12.3 Migration Script Format

Migrations are versioned Python scripts in `migration/versions/`:

```
migration/versions/
  001_initial_schema.py
  002_add_episode_tables.py
  003_add_diagnosis_fields.py
```

Each script implements `up()` and `down()` methods with warehouse-specific DDL. Migrations are tested against all three warehouse targets.

---

## 13. Deployment

### 13.1 Container Image

ASRE ships as a single Docker image:

```
asre-engine:v1.x.x
```

Contents:

- Python 3.11 runtime
- ASRE Python package
- dbt-core + all three warehouse adapters (Snowflake, BigQuery, Redshift)
- AHRQ CCS grouper data files
- CLI entry point

### 13.2 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ASRE_CUSTOMER_ID` | Yes | Customer identifier |
| `ASRE_CONFIG_PATH` | Yes | Path to customer config directory |
| `ASRE_WAREHOUSE_TYPE` | Yes | `snowflake`, `bigquery`, `redshift` |
| `ASRE_WAREHOUSE_CREDENTIALS` | Yes | Connection string or path to credentials file |
| `ASRE_RUN_MODE` | No | `full` or `incremental` (default: `incremental`) |
| `ASRE_LOG_LEVEL` | No | `DEBUG`, `INFO`, `WARN`, `ERROR` (default: `INFO`) |
| `ASRE_ALERT_WEBHOOK_URL` | No | Webhook URL for alerts |
| `ASRE_DRY_RUN` | No | `true` to run pipeline without writing outputs |

### 13.3 CLI

```bash
# Core pipeline
asre run --mode full              # Full historical reprocessing
asre run --mode incremental       # Process since last watermark (default)
asre run --resume <run_id>        # Resume failed run from last checkpoint

# Configuration
asre validate-config              # Validate YAML config only
asre test-connection              # Test warehouse connectivity
asre status                       # Show pipeline status

# Schema management
asre migrate                      # Run pending schema migrations

# Facility management
asre facilities --unresolved      # List unresolved facilities
asre facilities resolve <id>      # Map unresolved facility to canonical ID

# Episode management
asre episodes --recompute         # Recompute episodes without full pipeline run

# Diagnostics
asre inspect run <run_id>         # Show run details, stage timings, error counts
asre inspect encounter <id>       # Show encounter with all source events
asre inspect errors --last-run    # Show failed events from last run
```

### 13.4 Orchestration Integration

ASRE does not include its own scheduler. It is designed to be triggered by the customer's existing orchestration:

- **Airflow:** `BashOperator` or `DockerOperator` calling `asre run`.
- **dbt Cloud:** Custom job step.
- **Cron:** `0 * * * * docker run asre-engine:latest asre run`.
- **Cloud Scheduler + Cloud Run / ECS:** Scheduled container execution.

### 13.5 Infrastructure Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 4 vCPU |
| Memory | 4 GB | 8 GB |
| Disk | 10 GB | 20 GB (for registry files, logs) |
| Network | Outbound to warehouse | Same VPC as warehouse |

---

## 14. Security & Compliance

### 14.1 PHI Handling

- All PHI remains in the customer's environment at all times.
- ASRE does not transmit PHI to any external endpoint.
- Alert webhooks contain only aggregate metrics, never PHI.
- Audit logs reference entity IDs, not patient-level data.

### 14.2 Access Control

- ASRE uses the customer's warehouse credentials and inherits their access control model.
- Warehouse role should have read access to source tables and write access to ASRE output schema only.
- Container runs with a dedicated service account (no root).

### 14.3 Encryption

- Data at rest: customer warehouse encryption (managed by warehouse).
- Data in transit: TLS for all warehouse connections.
- Config files: support `${ENV_VAR}` substitution for secrets (no plaintext credentials in YAML).

---

## 15. Billing & Licensing

### 15.1 Model

ASRE is licensed as an annual subscription with volume tiers. No usage-based metering or telemetry in v1.

| Tier | Volume (encounters/month) | Notes |
|------|--------------------------|-------|
| Starter | Up to 50,000 | Single source feed type (e.g., ADT only) |
| Standard | Up to 250,000 | Multiple source feeds, full reconciliation |
| Enterprise | 250,000+ | Custom, negotiated |

Volume is defined as the number of unique encounters in `admission_events_unified` produced per calendar month. Customers can self-report or provide read-only access to `asre_quality_metrics` (which contains `encounters_created` and `encounters_updated` counts per run, no PHI).

### 15.2 What's Included

- ASRE Docker image (versioned releases)
- Customer config onboarding support
- Access to updated public registry files (NPI, CCN, HIFLD)
- AHRQ CCS grouper data files (updated with annual ICD-10 releases)
- Patch and minor version updates

### 15.3 What's Not Included

- Custom adapter development (billed separately or SOW)
- Custom condition grouper development
- On-site deployment engineering
- Warehouse infrastructure costs (customer-owned)

### 15.4 Future: Usage-Based Metering

If usage-based billing is adopted later, it would require a lightweight telemetry component that posts aggregate run metrics (encounter counts, run duration — never PHI) to an ASRE-hosted billing endpoint. This is explicitly out of scope for v1 but the `asre_quality_metrics` table already captures the data needed to support it.

---

## 16. Project Structure

```
asre/
├── cli/
│   └── main.py                  # CLI entry point (core + diagnostic commands)
├── config/
│   ├── loader.py                # YAML config loader + validator
│   └── schema.py                # Pydantic models for config validation
├── ingest/
│   ├── base.py                  # IngestAdapter interface
│   ├── snowflake.py
│   ├── bigquery.py
│   └── redshift.py
├── canonicalize/
│   ├── mapper.py                # Field mapping engine
│   └── event_type_resolver.py   # Event type derivation
├── facility/
│   ├── normalizer.py            # String normalization pipeline (campus-aware)
│   ├── matcher.py               # Fuzzy/exact matching
│   └── registry.py              # Registry loader (NPI, CCN, HIFLD)
├── stitch/
│   └── encounter_stitcher.py    # Encounter stitching algorithm
├── dedup/
│   └── deduplicator.py          # Deduplication logic
├── reconcile/
│   └── reconciler.py            # Cross-source reconciliation (context-dependent priority)
├── score/
│   └── confidence_scorer.py     # Confidence scoring engine
├── episode/
│   ├── episode_stitcher.py      # Episode stitching algorithm
│   ├── episode_scorer.py        # Episode-level confidence scoring
│   └── condition_grouper.py     # Episode type classification dispatcher
├── groupers/
│   ├── base.py                  # ConditionGrouper abstract interface
│   └── ahrq_ccs.py              # AHRQ CCS ICD-10 grouper implementation
├── quality/
│   ├── metrics.py               # Metric computation
│   └── alerter.py               # Threshold evaluation + webhook dispatch
├── observability/
│   ├── metrics.py               # Per-stage timing and throughput tracking
│   └── logger.py                # Structured JSON logging with stage context
├── migration/
│   ├── migrator.py              # Schema version detection + migration runner
│   └── versions/                # Versioned migration scripts
│       ├── 001_initial_schema.py
│       └── ...
├── pipeline/
│   └── runner.py                # Pipeline orchestration (stage sequencing, checkpointing)
├── models/
│   ├── canonical_event.py       # Canonical event dataclass
│   ├── encounter.py             # Encounter dataclass
│   ├── episode.py               # Episode dataclass
│   ├── diagnosis.py             # Diagnosis code models
│   └── batch.py                 # EventBatch dataclass
├── dbt_project/
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/
│   │   ├── intermediate/
│   │   └── marts/
│   │       ├── admission_events_unified.sql
│   │       ├── asre_encounters_detail.sql
│   │       ├── asre_episodes.sql
│   │       ├── asre_facility_registry.sql
│   │       ├── asre_quality_metrics.sql
│   │       ├── asre_run_metrics.sql
│   │       └── asre_audit_log.sql
│   └── tests/
├── customer_config/              # Per-customer config (mounted volume)
│   └── <customer_id>/
│       ├── config.yaml
│       ├── sources/
│       │   ├── adt_vendor_x.yaml
│       │   ├── claims_clearinghouse.yaml
│       │   └── auth_portal.yaml
│       └── facility_aliases.yaml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── README.md
```

---

## 17. Testing Strategy

### 17.1 Unit Tests

- Config loader: validates all YAML schema permutations.
- Field mapper: source columns → canonical columns.
- Event type resolver: HL7 trigger + patient class → normalized event type.
- Facility normalizer: string normalization pipeline (including campus token preservation).
- Encounter stitcher: stitching logic with known input/output pairs.
- Deduplicator: duplicate identification and resolution.
- Confidence scorer: score computation for known signal combinations.
- Episode stitcher: episode grouping with known encounter sets.
- Condition grouper: DRG/ICD-10 → episode type classification.
- Reconciler: context-dependent priority resolution.

### 17.2 Integration Tests

- End-to-end pipeline run with synthetic data (including episode stages).
- Warehouse adapter tests against local containers (Postgres as stand-in for warehouse-specific SQL).
- Config validation against example customer configs.
- Schema migration tests against all three warehouse targets.

### 17.3 Synthetic Test Data

A test data generator produces realistic ADT/claims/auth data with configurable anomalies (duplicates, missing discharges, facility name variations, timestamp mismatches, readmissions, post-acute transitions).

### 17.4 Snapshot Testing

Golden-file tests use **pytest-syrupy** for snapshot management:

- Known input datasets with expected output encounters and episodes.
- Any change to stitching, dedup, reconciliation, or episode logic must not alter snapshots without explicit approval.
- Use `--snapshot-update` to accept intentional changes.
- CI blocks on unapproved snapshot changes; diffs are visible in PRs.

---

## 18. Future Considerations (Out of Scope for v1)

### 18.1 REST API (v1.1)

A lightweight FastAPI service running alongside (or within) the ASRE container. Not required for core pipeline operation, but needed for operational usability as deployments scale.

#### Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Container liveness check |
| `/status` | GET | Last run status, timestamp, summary metrics |
| `/status/history` | GET | Recent run history (last N runs) |
| `/config/validate` | POST | Upload and validate a YAML config without applying it |
| `/config/sources` | GET | List configured source feeds and their status |
| `/facilities/unresolved` | GET | List facilities flagged `FACILITY_NEW_UNREVIEWED` |
| `/facilities/{id}/resolve` | POST | Map an unresolved facility to an existing canonical ID or confirm as new |
| `/facilities/{id}/aliases` | POST | Add aliases to an existing facility |

#### Design Notes

- Read-only for pipeline data (no writes to `admission_events_unified` via API).
- Facility review endpoints write to `asre_facility_registry` only.
- Auth: API key or mTLS (customer's choice). No user management — this is an ops API, not a user-facing app.
- The API is optional. Everything it exposes can also be done via CLI + direct warehouse queries.

### 18.2 Other Future Enhancements

| Feature | Design Hook |
|---------|------------|
| ML-based confidence scoring | Swap `confidence_scorer.py` implementation |
| ML-based episode type classification | Extend episode layer with trained grouper model |
| UI for facility review | Build on top of v1.1 facility API endpoints |
| Multi-tenant SaaS | Requires control plane, tenant isolation, credential management |
| Custom condition-episode groupers | Implement `ConditionGrouper` interface (CMS Bundled Payment, Prometheus, etc.) |
| Usage-based billing telemetry | Lightweight metering endpoint; data already in `asre_quality_metrics` |
| Eligibility feed ingestion | Add X12 270/271 source type and mapping config |

---

## 19. Glossary

| Term | Definition |
|------|-----------|
| ADT | Admit-Discharge-Transfer; HL7 message category for patient movement events |
| AHRQ CCS | Agency for Healthcare Research and Quality Clinical Classifications Software; a public-domain ICD-10 grouper |
| Canonical Event | A source record mapped to ASRE's standard schema |
| Condition Grouper | A pluggable component that classifies diagnosis codes into clinically meaningful categories for episode typing |
| Encounter | A logical grouping of events representing a single episode of care at one facility |
| Episode of Care | A longitudinal grouping of related encounters across facilities and time, representing a patient's full care journey for a condition or event |
| Encounter Stitching | The process of grouping related canonical events into encounters |
| Episode Stitching | The process of grouping related encounters into a single episode of care |
| Continuum of Care | The full sequence of care settings a patient moves through (e.g., ED → acute → SNF → home health) |
| Confidence Score | A 0-1 measure of how reliable/complete an encounter record is |
| Facility Normalization | Resolving variant facility names to a single canonical identity |
| Idempotent | A property where the same operation applied multiple times produces the same result as applying it once |
| Post-Acute | Care settings following an acute hospitalization (SNF, LTACH, rehab, home health) |
| Readmission | A new acute admission within a defined window after a prior discharge |
| Watermark | A timestamp tracking the last successfully processed record, used for incremental runs |
| PHI | Protected Health Information (HIPAA) |
| NPI | National Provider Identifier |
| CCN | CMS Certification Number |
| DRG | Diagnosis-Related Group |
| LOS | Length of Stay |
| LTACH | Long-Term Acute Care Hospital |
| SNF | Skilled Nursing Facility |
