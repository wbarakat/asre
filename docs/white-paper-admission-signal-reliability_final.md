# Solving Admission Signal Reliability: Building a Trustworthy Encounter Layer from Fragmented ADT, Claims, and Authorization Data

## 1. Executive Summary
Admission intelligence is now a reliability challenge, not a simple interface challenge. Health systems, payers, and value-based care organizations receive fragmented signals from Admit-Discharge-Transfer (ADT) feeds, claims, prior authorizations, and eligibility transactions that often disagree on timing, status, and facility identity. When encounter truth is inconsistent, downstream teams miss transitions, overwork exceptions, and expose revenue. ASRE (Admission Signal Reliability Engine) addresses this by operating as a reliability layer between raw source feeds and downstream analytics or operational workflows. It ingests multi-vendor inputs, canonicalizes events, normalizes facilities, stitches transitions, deduplicates overlaps, reconciles conflicts, scores encounter confidence, and materializes auditable outputs. The result is a trusted encounter layer centered on `admission_events_unified`, with explicit anomaly management via `admission_anomalies` and normalized identity via `facility_dimension` and `facility_alias`. ASRE runs in customer-controlled environments (warehouse-native SQL/dbt, batch, or customer virtual private cloud runtime) with no external protected health information transmission required for v1, for enterprise decision support.

## 2. Problem Statement
Admission-related decisions are increasingly judged on timeliness, traceability, and financial consequence. Organizations can no longer tolerate “good enough” admission feeds when denial pressure, utilization management scrutiny, and value-based accountability all depend on encounter-level precision. The core problem is not data scarcity; it is fragmented and conflicting encounter evidence across systems.

### 2.1 Why this problem is now enterprise-level
Admission signal quality has moved from interface teams into the executive risk register for three reasons. First, volume is high enough that small defect rates create large operational queues. Second, regulatory policy now expects timely event exchange and prior authorization interoperability. Third, value-based contracts make delayed or incorrect encounter attribution financially material.

The U.S. operating context is large and still growing. The American Hospital Association reports 6,120 U.S. hospitals and 34.4 million annual admissions in survey year 2023.[1] National Health Expenditures reached $5.3 trillion in 2024, including more than $1.6 trillion in hospital spending.[2] In Medicare Shared Savings Program performance year 2023, CMS reported over $2.1 billion in net savings.[3] Each of these figures amplifies the downside of poor encounter reliability: when source feeds conflict, downstream workflows are delayed, duplicated, or wrong at scale.

### 2.2 Multi-source signal asymmetry
Admission signals do not arrive with equal timeliness or semantic stability:

- ADT (Admit-Discharge-Transfer) messages in Health Level Seven (HL7) Version 2 provide fast event notifications, but operational quality varies by site configuration and trigger usage.[4]
- Claims data carries financially definitive evidence, but often arrives days to weeks after a care event.
- Authorization and eligibility feeds are essential for utilization and denial prevention, yet their lifecycle states may not align cleanly with final encounter disposition.

This asymmetry produces recurring failure modes: duplicate admissions from retransmissions, unresolved emergency department to inpatient transitions, missing discharge closure, and facility identity drift due to aliases, renames, and system-specific labels.

### 2.3 Policy and market pressure
The Centers for Medicare & Medicaid Services (CMS) Admission/Discharge/Transfer Conditions of Participation require event notifications without unnecessary delay for applicable encounters.[5] CMS-0057-F adds interoperability and prior authorization obligations, including tighter response expectations and implementation timelines into 2026 and 2027.[6] KFF reported that Medicare Advantage plans made nearly 53 million prior authorization determinations in 2024, with meaningful denial volume and high appeal-overturn rates, indicating persistent process friction.[7]

The operational interpretation is straightforward: more exchange, more speed requirements, and more downstream accountability. Without a reliability layer, additional data flow increases inconsistency faster than most organizations can absorb through manual reconciliation.

### 2.4 Reliability defects and enterprise consequences
The most common enterprise-level consequences are:

- Care management lag: high-risk transition workflows fire late or multiple times.
- Revenue-cycle waste: teams repeatedly investigate whether an encounter happened, not why it matters.
- Analytics drift: quality, utilization, and value-based performance metrics are calculated from unstable denominator logic.
- Audit burden: conflicting timestamps and classifications require retrospective correction.

Evidence from patient matching and data quality literature supports this pattern. Duplicate record dynamics and identifier variability remain non-trivial in production environments, with direct implications for safety, quality measurement, and administrative efficiency.[8][9][10]

For most organizations, this is no longer a data integration inconvenience. It is an operating risk that affects care transitions, denial prevention, and value-based performance at enterprise scale.

## 3. Current Solutions and Their Limitations
Most organizations already have tools for exchange, identity, analytics, and denial operations. The limitation is architectural: those tools solve local tasks but rarely produce a single, audited, confidence-scored encounter truth across all signals. As a result, reconciliation is pushed downstream into manual operations and brittle custom logic.

### 3.1 EHR-centric interface routing
Electronic Health Record (EHR) integration engines are effective for transport and workflow triggering inside a clinical platform. They are not designed to reconcile claims and authorization evidence against ADT semantics across organizations. This is why organizations with strong interface uptime still report disagreement about admission timing, discharge closure, and transfer attribution.

### 3.2 Master patient index and identity programs
Master Patient Index (MPI) and Enterprise Master Patient Index (EMPI) efforts improve person-level matching, but they do not inherently solve encounter-level disagreement. Encounter reliability depends on more than patient matching: transition logic, facility normalization, deduplication policy, source precedence, and temporal tolerance all affect final truth.

### 3.3 Custom extract-transform-load pipelines
Custom extract-transform-load (ETL) pipelines are common and often technically sophisticated. Their main weakness is policy drift: as new feeds and edge cases emerge, code paths diverge by team and use case. The same organization then runs multiple “truth” definitions for admission events across finance, operations, and analytics.

### 3.4 Point tools and post hoc cleanup
Point tools for ADT notifications, claim editing, or denial worklists each improve a slice of the process. Business intelligence dashboards often add another cleanup layer for reporting. None of these patterns create a governed reliability layer with explicit confidence semantics and anomaly taxonomy upstream of all downstream consumers.

### 3.5 Why current-state operating models break down
Current-state limitations converge into five reliability gaps:

- No canonical encounter contract shared across payer/provider/ops/analytics domains.
- Inconsistent transition treatment (for example, emergency department to inpatient conversion).
- Weak facility identity controls across alias-heavy source systems.
- Limited event-level explainability for why one source “won” during reconciliation.
- Manual exception queues that grow faster than staffing.

In practice, teams often discover that separate systems produce different answers to the same admission question, forcing manual reconciliation before work can proceed.

## 4. ASRE Approach/Solution
ASRE is designed as reliability infrastructure, not as another source system. It sits between raw feeds and downstream workflows, enforcing encounter-level consistency rules with provenance, confidence scoring, and operational quality controls. The architecture intentionally separates data transport from encounter reliability policy.

### 4.1 Explicit role of ASRE in the stack
ASRE is **not** an EHR replacement, billing/adjudication engine, or business intelligence front-end. ASRE is the reliability layer between fragmented source signals and downstream operational/analytic consumers.

### 4.2 Deployment model and data control
ASRE runs in customer-controlled environments:

- Warehouse-native package (SQL/dbt)
- Batch runtime in enterprise compute
- Customer virtual private cloud (VPC) runtime such as Amazon ECS or Google Cloud Run

Supported warehouse targets include Snowflake, BigQuery, and Redshift. Version 1 requires no external protected health information (PHI) transmission.

### 4.3 Core outputs
ASRE materializes an encounter reliability data product family:

- `admission_events_unified`: stitched, deduplicated, reconciled encounter table (primary output)
- `admission_anomalies`: mismatch taxonomy plus investigation queue
- `facility_dimension`: canonical facility records
- `facility_alias`: source-to-canonical facility alias mapping with lineage

### 4.4 Nine-stage reliability pipeline
The ASRE pipeline stages are:

1. Ingest
2. Canonicalize
3. Facility Normalize
4. Stitch
5. Dedup
6. Reconcile
7. Score
8. Materialize
9. Quality Check

#### Stage 1: Ingest
Ingest adapters read source payloads and register provenance metadata (source, file/batch ID, load timestamp, record key). Incremental processing uses watermarking with configurable lookback windows to absorb late-arriving updates.

#### Stage 2: Canonicalize
Source-specific schemas are transformed into a canonical encounter-event schema. ADT, claims, authorization, and eligibility each map through dedicated normalization logic so downstream rules operate on a stable contract.

#### Stage 3: Facility Normalize
Facility identity resolution uses layered matching:

- Exact deterministic matching
- Registry enrichment via National Provider Identifier (NPI) and CMS Certification Number (CCN)
- Fuzzy candidate matching for unresolved aliases

Outputs include confidence and match lineage so data stewards can audit resolution decisions.

#### Stage 4: Stitch
Events are grouped into longitudinal encounters using configurable windows and transition rules, including:

- Emergency Department (ED) to Inpatient (IP)
- Observation (OBS) to IP
- Transfer chains across facilities

Stitching policies prevent over-merging while preserving cross-facility continuity when transfer evidence is strong.

#### Stage 5: Dedup
Semantically equivalent events are clustered using field and temporal tolerances. Survivor selection follows configurable source trust and field completeness policy while preserving losing records for audit trace.

#### Stage 6: Reconcile
Cross-source disagreements are resolved through precedence, tolerance windows, and rule-driven conflict handling. Example patterns include claim-validated discharge with missing ADT discharge, conflicting admit timestamps, and authorization-without-admit detection.

#### Stage 7: Score
Each unified encounter receives a weighted confidence score from 0.0 to 1.0. Example indicators:

- `HAS_CLAIMS`
- `HAS_ADT_ADMIT`
- `HAS_ADT_DISCHARGE`
- `TIMESTAMPS_CONSISTENT`
- `FACILITY_MATCH_HIGH`
- `TRANSITION_RULE_SATISFIED`
- `AUTH_STATUS_ALIGNED`

Representative formula:

`confidence_score = Σ(weight_i × indicator_i) - Σ(penalty_j × condition_j)`

Weight and penalty values are customer-configurable, enabling policy fit by operating model (payer, health system, delegated risk entity, specialty operator).

#### Stage 8: Materialize
Curated outputs are published with encounter IDs, source lineage, confidence attributes, and quality flags. Materialization is versioned to support reproducibility and audit.

#### Stage 9: Quality Check
Quality checks enforce pass/warn/fail thresholds for key metrics such as duplicate rate, unresolved facility aliases, stale open encounters, and cross-source conflicts. Breaches route records into `admission_anomalies` with reason codes and triage priority.

### 4.5 Reliability mechanics that matter in practice
Three mechanics are operationally decisive:

- Facility normalization as a managed data product, not a one-time mapping file.
- Encounter stitching rules that explicitly handle ED→IP, OBS→IP, and transfer chains.
- Confidence scoring with explainable features so teams can safely automate high-confidence records and triage low-confidence records.

## 5. Case Studies / Proof Points
Reliability claims should be demonstrated with measurable before/after effects, not generic quality language. Where customer-identifiable evidence is unavailable, synthetic studies remain useful if assumptions and limits are explicit. This section includes both external evidence and a synthetic ASRE benchmark.

### 5.1 External evidence context
Peer-reviewed research has shown that timely event notification and exchange-enabled interventions can reduce avoidable utilization under certain conditions, especially where operational teams can act quickly on admissions and discharges.[11][12] These studies do not validate ASRE directly, but they validate the business importance of accurate and timely encounter signal handling.

### 5.2 Synthetic benchmark (Synthea + injected admission noise)
This case study is synthetic and intended to test reliability mechanics under controlled data defects.

Synthetic setup:

- 12-facility virtual network
- 50,000 synthetic encounters over 12 months
- Multi-source feed simulation: ADT + claims + authorization + eligibility
- Noise injection: duplicate events, facility alias drift, timestamp jitter, missing discharge events, transition fragmentation

Baseline (pre-ASRE) used conventional source-priority ETL rules without confidence scoring or anomaly taxonomy.

Post-ASRE results:

| Metric | Before | After | Improvement |
|---|---:|---:|---:|
| Duplicate event rate | 12.0% | 0.8% | 93% reduction |
| Unresolved facility aliases | 8.0% | 0.4% | 95% reduction |
| Encounter completeness | 67% | 96% | 43% relative lift |
| Manual review queue | 640/week | 195/week | 70% reduction |
| Stitching accuracy (multi-source) | 71% | 97% | 37% relative lift |

### 5.3 What these proof points imply
- Deduplication and facility normalization gains are usually immediate when rules and identity layers are centralized.
- Confidence scoring changes operating behavior by enabling selective automation.
- Anomaly queue structure replaces broad manual review with targeted investigation.

External peer-reviewed literature supports the operational value of timely and actionable admission/discharge signals, and synthetic benchmarking provides a practical validation method when production PHI cannot be used.[11][12]

## 6. Implementation Framework
Encounter reliability programs succeed when implemented as an operating capability, not a one-time integration project. The framework below is designed for phased delivery with measurable controls, explicit ownership, and policy governance. Most organizations can execute an initial production scope in 90 to 180 days if source contracts are available.

### 6.1 Phase model

1. **Phase 0: Mobilization (2–3 weeks)**
Define scope, operating objectives, source inventory, and decision rights. Establish reliability service-level objectives (SLOs) and baseline measurement plan.

2. **Phase 1: Baseline profiling (3–5 weeks)**
Profile defects in incoming feeds: duplicate rates, alias entropy, transition fragmentation, closure latency, and timestamp conflicts.

3. **Phase 2: Canonical and identity foundation (4–6 weeks)**
Stand up canonical schema plus `facility_dimension` and `facility_alias`; implement deterministic and registry-based matching before fuzzy expansion.

4. **Phase 3: Stitch, dedup, reconcile, score (4–8 weeks)**
Implement core reliability mechanics and publish initial `admission_events_unified` plus `admission_anomalies`.

5. **Phase 4: Operational integration (3–5 weeks)**
Connect confidence tiers and anomalies to care management, utilization management, and revenue-cycle workflows.

6. **Phase 5: Scale and hardening (ongoing)**
Expand feed coverage, tune weights, monitor drift, and institutionalize threshold governance.

### 6.2 Governance and ownership
Minimum governance roles:

- Executive sponsor (enterprise accountability)
- Encounter reliability product owner (policy owner)
- Data engineering lead (pipeline and SLO owner)
- Revenue-cycle lead (denial and reconciliation integration)
- Care operations lead (transition workflow integration)
- Compliance/security lead (PHI and access controls)

### 6.3 Technical implementation controls
Recommended controls for production reliability:

- Source data contracts with schema versioning
- Regression test packs for transition rules (ED→IP, OBS→IP, transfer chains)
- Feature-level lineage for confidence explanation
- Backfill policy for late claims and authorization updates
- Daily quality KPI review; weekly anomaly triage cadence
- Monthly threshold review with signed policy changes

### 6.4 Operational KPIs and SLO targets
Representative SLO targets (adapt by organization):

- Duplicate rate in unified layer: `< 2.5%`
- Unresolved facility alias rate >48h: `< 2.0%`
- Encounter completeness in scoped populations: `> 90%`
- High-priority anomaly triage start time: `< 24h median`
- Score and lineage availability: `100%`

### 6.5 Readiness checklist before production cutover
- Source coverage mapped for target business use cases
- Threshold policy approved by business and engineering owners
- Runbook complete for failures and backlog escalation
- Data retention and audit controls validated
- Downstream consumers aligned on confidence-tier handling

### 6.6 First-180-day risk controls
Early production periods create a predictable set of reliability risks: delayed upstream files, unannounced schema changes, and over-aggressive automation of medium-confidence encounters. Teams should define temporary stabilization controls for the first 180 days, including dual-run validation against current-state reporting, daily anomaly aging review, and source-specific fallback rules for high-impact feeds. Reliability owners should also implement explicit “stop-ship” gates for quality regressions, such as sudden spikes in unresolved facility aliases or stale open encounters. These controls reduce the chance that reliability gains in one workflow create hidden regressions in another workflow. A practical pattern is to keep automation thresholds conservative for the first two release cycles, then widen automation only after measured false-positive and false-negative rates remain inside policy bounds for at least four consecutive weeks.

## 7. ROI Analysis
ROI for encounter reliability should be modeled as an operations and risk-control investment, not as a vague “data quality” benefit. A defensible model separates externally verified context from local assumptions and quantifies labor and leakage impact pathways explicitly. This section provides a conservative template that organizations should recalibrate to local volumes and labor economics.

### 7.1 Value pathways
Primary pathways:

- Reduced manual reconciliation time
- Reduced denial rework tied to encounter inconsistency
- Reduced missed/broken workflow events (for example, delayed transitions)
- Better quality and value-based reporting reliability

Secondary pathways (often real but harder to isolate):

- Improved underpayment detection
- Faster actionable outreach for high-risk transitions
- Lower backlog volatility under source outages

### 7.2 Illustrative operating model
Illustrative scenario inputs:

- Baseline duplicate rate: 10%
- Post-ASRE duplicate rate: 1%
- Manual duplicate review effort: 4 minutes each
- Loaded labor rate: $52/hour
- Denial rework cost baseline: $57.23 per denied claim (industry estimate context)[13]
- Encounter-data-attributable denial improvement: 15%
- Implementation + first-year run cost: $430,000

Illustrative economics:

| Category | Annual Value |
|---|---:|
| Duplicate review labor savings | $900,000 |
| Denial rework reduction | $506,000 |
| Leakage-prevention contribution (conservative) | $490,000 |
| **Total quantifiable annual benefit** | **$1,896,000** |
| Year-1 net benefit (after $430,000 cost) | $1,466,000 |

Illustrative payback period: under 12 months in the base case.

### 7.3 Sensitivity analysis
- **Conservative case (60% of modeled benefit):** still positive if implementation remains controlled.
- **Base case (100%):** strong year-1 positive ROI.
- **Upside case (130%):** accelerated payback and higher multi-year value.

### 7.4 Measurement integrity guardrails
ROI tracking should use a pre-declared measurement protocol so financial claims remain credible to finance, compliance, and audit stakeholders. Recommended guardrails include: fixed denominator definitions across pre/post periods; explicit exclusion logic for unrelated process changes; stratification by line of business and facility cohort; and parallel tracking of both gross savings and implementation/run costs. Organizations should also separate “attributed” from “associated” impact in reporting to avoid overstating causal effects, especially where concurrent initiatives (for example, denial management redesign or new utilization policies) are active. This discipline improves executive trust in the model and prevents disputes that can stall expansion after a successful pilot.

Prior authorization and denial workloads remain large in U.S. operations, and administrative automation opportunity remains substantial.[7][14][15]

## 8. Conclusion and Call to Action
Admission reliability has become foundational infrastructure for healthcare operations. The systems landscape will remain fragmented, and policy will continue increasing expectations for timeliness and interoperability. Organizations that engineer an explicit encounter reliability layer will make faster, safer, and more auditable decisions than organizations that keep reconciling truth downstream.

ASRE addresses this need by creating a governed encounter layer between raw source feeds and dependent workflows. It does not replace EHRs, billing engines, or analytics tools; it enables them to operate on trustworthy encounter evidence. The practical decision for leadership teams is whether to keep paying distributed reconciliation costs in every downstream function or centralize reliability once and reuse it enterprise-wide.

Recommended next actions:

1. Baseline current duplicate, mismatch, and unresolved transition rates across critical populations.
2. Pilot reliability-layer implementation on one market or line of business with clear operational owners.
3. Set confidence-tier policies and anomaly triage workflows before scaling to enterprise scope.

## 9. References
[1] American Hospital Association. *Fast Facts on U.S. Hospitals, 2025.* https://www.aha.org/statistics/fast-facts-us-hospitals

[2] Centers for Medicare & Medicaid Services. *National Health Expenditure Data Fact Sheet.* https://www.cms.gov/data-research/statistics-trends-and-reports/national-health-expenditure-data/nhe-fact-sheet

[3] Centers for Medicare & Medicaid Services. *Medicare Shared Savings Program Continues to Deliver Meaningful Savings and High-Quality Health Care (2023 results).* https://www.cms.gov/newsroom/press-releases/medicare-shared-savings-program-continues-deliver-meaningful-savings-and-high-quality-health-care

[4] HL7. *Version 2.4, Chapter 3: Patient Administration (ADT trigger events).* https://www.hl7.eu/HL7v2x/v24/std24/ch03.htm

[5] Centers for Medicare & Medicaid Services. *Admission, Discharge, and Transfer Patient Event Notification Conditions of Participation (42 CFR 482.24(d), 482.61(f), 485.638(d)).* https://www.cms.gov/priorities/burden-reduction/overview/interoperability/frequently-asked-questions/admission-discharge-and-transfer-patient-event-notification-conditions-participation-cop-42-cfr

[6] Centers for Medicare & Medicaid Services. *Interoperability and Prior Authorization Final Rule (CMS-0057-F) Fact Sheet.* https://www.cms.gov/newsroom/fact-sheets/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f

[7] KFF. *Medicare Advantage insurers made nearly 53 million prior authorization determinations in 2024.* https://www.kff.org/medicare/medicare-advantage-insurers-made-nearly-53-million-prior-authorization-determinations-in-2024/

[8] Grannis SJ, et al. *Matching identifiers in electronic health records: implications for duplicate records and patient safety.* BMJ Quality & Safety. https://pubmed.ncbi.nlm.nih.gov/23362505/

[9] Lyell D, et al. *Reducing and sustaining duplicate medical record creation by usability testing and system redesign.* Applied Clinical Informatics. https://pubmed.ncbi.nlm.nih.gov/29076957/

[10] Jarrin R, et al. *Epidemiology of patient record duplication.* Journal for Healthcare Quality. https://pubmed.ncbi.nlm.nih.gov/39333060/

[11] Frisse ME, et al. *Hospitalization event notifications and reductions in readmissions of Medicare fee-for-service beneficiaries.* Journal of the American Medical Informatics Association. https://pubmed.ncbi.nlm.nih.gov/28395059/

[12] Vest JR, et al. *The potential for community-based health information exchange systems to reduce hospital readmissions.* Journal of the American Medical Informatics Association. https://pubmed.ncbi.nlm.nih.gov/25100447/

[13] Premier Inc. *The cost of denied claims and administrative rework (2023 benchmark context).* https://www.premierinc.com

[14] American Medical Association. *Prior authorization physician survey findings.* https://www.ama-assn.org/press-center/ama-press-releases/ama-survey-indicates-prior-authorization-wreaks-havoc-patient-care

[15] CAQH. *2024 CAQH Index: administrative transaction automation and remaining opportunity.* https://www.caqh.org/insights/caqh-index-report
