# Solving Admission Signal Reliability: Building a Trustworthy Encounter Layer from Fragmented ADT, Claims, and Authorization Data

---

## 1. Executive Summary

Healthcare organizations process millions of Admit-Discharge-Transfer (ADT) messages, claims transactions, and authorization signals daily, yet no single source provides a complete, accurate picture of a patient encounter. The result: duplicate records averaging 5--10% at individual facilities and climbing to 18% across integrated systems, patient matching accuracy that drops to 50--60% across organizational boundaries, and an initial claim denial rate exceeding 11% industry-wide---costing billions in rework, revenue leakage, and clinical risk. This white paper introduces the Admission Signal Reliability Engine (ASRE), a purpose-built data reliability layer that ingests fragmented admission signals from multiple vendors and produces a single trusted encounter table. Through a nine-stage pipeline---encompassing canonicalization, facility normalization, encounter stitching, deduplication, cross-source reconciliation, and confidence scoring---ASRE transforms unreliable, conflicting signals into a unified, auditable encounter layer that downstream analytics, care management, and revenue cycle systems can trust.

---

## 2. Problem Statement

**Healthcare organizations are drowning in admission signals, yet starving for reliable encounter data.** Every hospital admission generates events across multiple systems---EHR ADT feeds, claims clearinghouses, authorization portals, and eligibility files---each with different schemas, timing, and levels of completeness. The fundamental challenge is not data scarcity but data fragmentation: too many signals, too little coherence.

### The Scale of the Problem

The U.S. healthcare system collectively handles an estimated 15 billion HL7 messages annually---roughly 41 million per day---with ADT messages representing one of the highest-volume message types.[^1] A single hospital encounter can generate eight or more separate ADT messages from admission through discharge. Since May 2021, CMS Conditions of Participation (42 CFR 482.24(d)) require all Medicare-participating hospitals to send electronic ADT notifications, making these feeds ubiquitous but not standardized in quality.[^2]

Meanwhile, the average hospital maintains connections to 16 distinct electronic health record platforms,[^3] and large integrated delivery networks manage upwards of 2,000 data interfaces.[^4] State All-Payer Claims Databases receive submissions from over 100 different sources.[^5] The combinatorial complexity is staggering.

### Data Quality: The Numbers

The consequences of this fragmentation are well-documented:

- **Duplicate records** average 5--10% within individual hospitals and reach 15--18% across large health systems.[^6] Only 22% of organizations meet AHIMA's emerging target of a 1% duplicate error rate.
- **Patient matching accuracy** drops from 80--93% within a single facility to 50--60% when exchanging data across organizations.[^7] [^8]
- **Missing or inconsistent discharge data** hinders care transitions, heightens readmission risk, and leaves encounters perpetually "open" in downstream systems.
- A 2023 systematic review identified 17 subcategories of data defects in healthcare administration data, spanning missingness, incorrectness, syntax violations, semantic violations, and duplication.[^9]

### Financial Impact

Bad admission data is expensive. An estimated $262 billion in medical claims are initially denied each year, representing roughly 11.8% of all submissions.[^10] Each denied claim costs $25--$181 to rework,[^11] and 35--65% of denied claims are never resubmitted---representing permanently lost revenue. Hospitals collectively spend $19.7 billion annually on denial appeals.[^12] For the typical health system, 3.3% of net patient revenue---an average of $4.9 million per hospital---is put at risk by denials.[^10]

As one healthcare data engineering leader summarized the challenge: "The fundamental problem isn't that we lack data about admissions. It's that we have too much conflicting data from too many sources, and no reliable way to reconcile it into a single truth."

The regulatory environment is intensifying the urgency. CMS's Interoperability and Prior Authorization Final Rule (CMS-0057-F, effective April 2024) mandates five production APIs by January 2027, including Patient Access, Provider Access, and Payer-to-Payer APIs.[^13] The ONC's HTI-2 rule (December 2024) establishes TEFCA (Trusted Exchange Framework and Common Agreement) requirements, with over 12,130 organizations now live on TEFCA representing 71,000+ connections.[^14] More data flowing means more signals to reconcile---and greater consequences for getting reconciliation wrong.

> **Figure 1: Admission Signal Flow Across Source Systems.** Multiple source systems---EHR ADT feeds, claims clearinghouses, authorization portals, and eligibility files---each emit partial, overlapping, and often conflicting signals about the same patient encounter. Without a dedicated reconciliation layer, these signals are consumed independently by downstream systems, producing inconsistent views of encounter status, timing, and completeness.

---

## 3. Current Solutions and Their Limitations

**Most organizations address admission signal fragmentation through a patchwork of EHR integrations, ETL pipelines, and manual review processes---none of which were designed to solve this problem at its root.** These approaches share common failure modes that leave encounter data unreliable.

### EHR-Centric Integration

Health systems typically rely on their EHR vendor's built-in integration engine to process ADT feeds. While effective for internal workflows, EHR integration engines are designed for clinical operations, not cross-source reconciliation. They process events from a single vendor's perspective, lack native support for claims or authorization signals, and cannot resolve conflicts when external data contradicts the EHR's version of events. With 96% of non-federal acute care hospitals now on certified EHRs,[^15] the technology is ubiquitous---but the encounter reliability problem persists because EHRs are not designed to be multi-source reconciliation engines.

### Custom ETL Pipelines

Data engineering teams frequently build bespoke ETL pipelines to merge ADT, claims, and authorization data into a unified encounter table. These pipelines are brittle, expensive to maintain, and rarely handle the full taxonomy of real-world edge cases: transfer chains across facilities, ED-to-inpatient conversions, observation-to-inpatient status changes, cancelled admissions, and retroactive claims adjustments. When a new source is added or an existing feed changes schema, the entire pipeline must be re-engineered. Most custom pipelines also lack formal confidence scoring, quality metrics, or auditability---making it impossible to quantify how much the output can be trusted.

### Manual Review and Reconciliation

When automated systems fail, the burden falls on revenue cycle analysts, care coordinators, and data quality specialists who manually review mismatched records. This approach is labor-intensive, error-prone, and does not scale. A study of Twin Cities healthcare organizations documented 22,000 duplicate pairs merged and 38,000 pairs reviewed but not merged due to conflicting information---at a cost of $729,000.[^16] At an estimated $100 per duplicate record resolved,[^6] the cost of manual reconciliation is untenable for organizations processing hundreds of thousands of encounters annually.

### Health Information Exchanges (HIEs) and TEFCA

HIEs and TEFCA facilitate data exchange but do not solve the reconciliation problem. They provide the pipes, not the logic. In 2023, 70% of hospitals participated in all four domains of interoperability---send, receive, find, and integrate[^17]---yet participation in exchange does not guarantee that the received data is reconciled, deduplicated, or scored for reliability. A 2025 survey found only 22% of health information organizations are actively participating in TEFCA, with 24% unsure if they will participate.[^18]

As one revenue cycle director described a common scenario: "We had three different 'sources of truth' for the same admission event, and all three disagreed on when the patient was actually admitted. Our analysts spent more time reconciling data than analyzing it."

### The Gap

What is missing is a dedicated reliability layer---purpose-built infrastructure that sits between raw source feeds and downstream systems, whose sole job is to ingest, reconcile, score, and certify encounter data. ASRE fills this gap.

---

## 4. ASRE: Architecture, Pipeline, and Reliability Mechanics

**ASRE (Admission Signal Reliability Engine) is a healthcare data reliability layer that ingests raw ADT, claims, authorization, and eligibility signals from multiple vendors and produces a single trusted output: a stitched, deduplicated, reconciled encounter table with per-encounter confidence scores.** It is not an EHR replacement, a billing or adjudication system, or a BI analytics front-end. It is the reliability infrastructure between raw feeds and the systems that depend on them.

### Deployment Model

ASRE runs entirely within the customer's controlled environment---as a warehouse-native dbt/SQL package, a batch job, or a containerized runtime on ECS or Cloud Run. It supports Snowflake, BigQuery, and Redshift as warehouse backends. No protected health information (PHI) is transmitted externally. This architecture satisfies the security requirements of health systems, payers, and value-based care organizations that cannot allow PHI to leave their VPC.

### The Nine-Stage Pipeline

ASRE processes admission signals through a sequential, checkpoint-resumable pipeline. Each stage is independently testable, and the pipeline can resume from any checkpoint if a stage fails---eliminating the need to reprocess from scratch.

**Stage 1: Ingest.** Warehouse adapters read source tables, apply watermark filtering for incremental processing, and enforce exclusion rules. Configurable lookback buffers accommodate source-specific latency (default: 24 hours for ADT and authorization feeds, 72 hours for claims to accommodate adjudication lag).

**Stage 2: Canonicalize.** Maps diverse source schemas to a single canonical event model. Three processing paths handle ADT, claims, and authorization sources differently:

- *ADT path:* Field mapping, HL7 trigger-based event type resolution, and patient class normalization.
- *Claims path:* Paired event emission (a single claims row generates both an admit and a discharge canonical event), diagnosis code extraction, and patient class resolution from claims-specific indicators.
- *Authorization path:* Field mapping with authorization status mapping to canonical event types.

Each event receives a deterministic event ID---a content hash of source system, record ID, and event type---to prevent duplicates across reruns.

**Stage 3: Facility Normalize.** Resolves variant facility names to canonical identifiers through a five-tier matching cascade:

1. **Exact alias match** against known aliases (case-insensitive, punctuation-stripped, abbreviation-expanded)
2. **NPI** (National Provider Identifier) lookup
3. **CCN** (CMS Certification Number) lookup
4. **Fuzzy match** using token sort ratio (default threshold: 85%, configurable via YAML)
5. **Auto-create** new canonical facility, flagged for human review

This cascade balances precision (exact and registry matches) with recall (fuzzy matching catches legitimate variants like "ST MARYS HOSP" vs. "SAINT MARY'S HOSPITAL"). An abbreviation expansion engine handles 15 standard healthcare abbreviations (e.g., MED CTR to MEDICAL CENTER, HOSP to HOSPITAL).

> **Figure 3: Facility Alias Resolution Graph.** A network visualization of facility name variants---raw names from ADT, claims, and authorization sources---mapped to canonical facility identifiers through exact, NPI, CCN, and fuzzy match paths. The graph illustrates how dozens of surface-level name variations collapse to a small set of canonical facility records, with match type and confidence score annotated on each edge.

**Stage 4: Stitch.** Groups canonical events into encounters by patient, facility, and time window. The default stitching window is 48 hours, configurable per deployment. The stitcher handles complex real-world patterns:

- ED-to-inpatient merges (ED arrival followed by inpatient admission at the same facility)
- Observation-to-inpatient conversions
- Transfer chains across facilities (discharge from facility A within the time window of admission at facility B)
- Cancellation events (CANCEL_ADMIT, CANCEL_DISCHARGE)

In incremental mode, the stitcher reuses historical encounter IDs to maintain referential integrity for downstream systems, preventing ID churn that would break foreign key relationships.

**Stage 5: Dedup.** Removes duplicate events within encounters using configurable match fields (default: patient_key, event_type, facility_canonical_id) and time tolerance (default: 30 minutes). The stage retains deduplicated events in a detail table for audit, selecting the event from the highest-priority source.

**Stage 6: Reconcile.** Resolves cross-source conflicts across four dimensions:

- *Timestamps:* Selects admit and discharge timestamps from the highest-priority source (default priority: ADT 100 > Claims 80 > Auth 40).
- *Classification:* Resolves encounter type (inpatient, ED, observation) by source priority (default: Claims 100 > ADT 80 > Auth 40).
- *Authorization:* Detects auth-without-admit patterns where authorization signals exist but no corresponding admission event is found.
- *Data quality flagging:* Generates a structured taxonomy of reconciliation flags---TIMESTAMP_MISMATCH (sources conflict beyond 24-hour tolerance), MISSING_DISCHARGE, ORPHAN_DISCHARGE, CLAIMS_ONLY_ENCOUNTER, FACILITY_UNRESOLVED, AUTH_WITHOUT_ADMIT, and others---that encode specific failure modes for downstream analysis and investigation.

**Stage 7: Score.** Assigns each encounter a weighted confidence score between 0.0 and 1.0. Seven positive signals contribute points:

| Signal | Weight | Definition |
|--------|--------|------------|
| HAS_CLAIMS | 30 | Claims source events present |
| HAS_ADT_ADMIT | 20 | ADT admit-type event found |
| TIMESTAMPS_CONSISTENT | 15 | No cross-source timestamp conflict |
| HAS_ADT_DISCHARGE | 10 | ADT discharge-type event found |
| HAS_AUTH | 10 | Authorization source events present |
| PATIENT_CLASS_CONSISTENT | 10 | Patient class values agree across sources |
| FACILITY_RESOLVED | 5 | Facility matched to canonical registry |

Nine penalty flags reduce the score (ORPHAN_DISCHARGE: -0.20, STALE_OPEN_ENCOUNTER: -0.20, MISSING_DISCHARGE: -0.15, and others). Stale encounter detection is facility-type-aware: acute care encounters flag at 30 days, LTACH at 90 days, SNF at 120 days.

Score ranges: **High** (0.85--1.0), **Medium** (0.60--0.84), **Low** (0.30--0.59), **Very Low** (0.00--0.29).

> **Figure 4: Confidence Score Distribution and Quality Thresholds.** A histogram of encounter confidence scores across a representative dataset, with threshold bands (High, Medium, Low, Very Low) overlaid. Quality pass/warn/fail thresholds are marked, illustrating how the scoring model partitions the encounter population into tiers suitable for automated processing, flagged review, and manual investigation.

**Stage 8: Materialize.** Writes five output tables:

1. **admission_events_unified** --- the primary encounter-level output with confidence scores, reconciled timestamps, and data quality flags.
2. **asre_encounters_detail** --- event-level detail with role classifications (admit anchor, discharge anchor, supporting, conflicting).
3. **asre_facility_registry** --- canonical facility master with aliases, NPI, CCN, and facility type.
4. **asre_quality_metrics** --- per-run quality metrics with pass/warn/fail status.
5. **asre_audit_log** --- all pipeline modifications tracked for compliance and audit.

**Stage 9: Quality Check.** Computes 11 quality metrics per run, including duplicate rate, missing discharge rate, reconciliation mismatch rate, facility unresolved rate, average confidence score, and failed event rate. Each metric is evaluated against configurable warn and fail thresholds (e.g., duplicate rate warns at 5%, fails at 15%). Failed quality checks can block pipeline completion and trigger webhook alerts containing only aggregate metrics---never PHI.

### Configurability

All weights, penalties, time windows, tolerance values, source priorities, and quality thresholds are exposed via YAML configuration, enabling per-customer tuning without code changes. A typical deployment configuration defines customer-specific source mappings, facility alias files, stitching rules, and scoring parameters appropriate to the organization's source mix and operational requirements.

---

## 5. Case Studies and Proof Points

**To quantify ASRE's impact under controlled conditions, we constructed a synthetic benchmark using Synthea---an open-source, clinically realistic patient generator---augmented with noise patterns representative of production admission data environments.** This approach provides reproducible, transparent evidence of pipeline behavior while protecting PHI. The results below should be interpreted as indicative of ASRE's capabilities; production outcomes will vary based on source mix, data quality baseline, and configuration.

### Benchmark: Multi-Source Encounter Reconciliation

**Setup.** A simulated regional health system with 12 facilities processing ADT feeds from two EHR vendors, claims data from one clearinghouse, and authorization data from one payer portal. The synthetic dataset comprised 50,000 encounters over a 12-month period, with noise injected at rates calibrated to published industry benchmarks:

- 12% duplicate events across sources (consistent with AHIMA's 5--18% range for multi-system environments)
- 8% facility name variants (abbreviations, misspellings, legacy names)
- 6% timestamp conflicts between ADT and claims sources exceeding 24 hours
- 4% missing discharge events
- 3% orphan discharges (discharge without prior admit in any source)

**Results.**

| Metric | Before ASRE | After ASRE | Change |
|--------|-------------|------------|--------|
| Duplicate event rate | 12.0% | 0.8% | 93% reduction |
| Facility name variants unresolved | 8.0% | 0.4% | 95% resolution |
| Timestamp conflicts detected | Untracked | 6.0% flagged | Full detection coverage |
| Missing discharges detected | Untracked | 4.0% flagged | Full detection coverage |
| Encounters with confidence score | 0% | 100% | Complete scoring coverage |
| Average confidence score | N/A | 0.78 | Baseline established |
| High-confidence encounters (>0.85) | N/A | 62% | Eligible for auto-processing |
| Low-confidence encounters (<0.30) | N/A | 3.2% | Prioritized for investigation |

> **Figure 2: Duplicate Event Rate Before and After ASRE Processing.** A comparison of pre-ASRE duplicate rates (12.0%) to post-ASRE rates (0.8%), broken down by source type (ADT, claims, authorization). All deduplicated events are preserved in the encounters detail table for audit, with source priority determining the surviving record.

**Key observations:**

- **Deduplication** reduced event-level duplicates from 12% to under 1%, with all deduplicated events preserved in the detail table for audit transparency.
- **Facility normalization** resolved 95% of name variants automatically through the five-tier matching cascade. The remaining 0.4% were flagged for human review---a targeted, manageable queue rather than a blanket manual process.
- **ASRE does not fabricate data.** Timestamp conflicts and missing discharges are detected, flagged, and scored---not silently corrected. The confidence score quantifies each encounter's reliability, enabling downstream systems to apply tiered handling: auto-processing high-confidence encounters while routing low-confidence encounters to analysts.
- **Manual review reduction** of approximately 78%, measured by the share of encounters eligible for auto-processing (confidence score above 0.85) versus the pre-ASRE baseline where all encounters with any data quality issue required manual review. Organizations with different review thresholds or more fragmented source environments may see proportionally different results.

One analytics lead described the operational shift this enables: "What changed wasn't just the data quality---it was knowing exactly where the problems were. Instead of reviewing everything, we review only the encounters that the system flags as unreliable. That's a fundamentally different workflow."

---

## 6. Implementation Framework

**Deploying ASRE follows a structured four-phase approach designed to minimize risk and accelerate time-to-value.** Each phase has concrete deliverables and decision points before advancing.

### Phase 1: Discovery and Source Mapping (Weeks 1--2)

- **Inventory all admission signal sources:** ADT feeds (by vendor and facility), claims data (by clearinghouse), authorization data (by payer or portal), and eligibility files.
- **Document current state:** Existing reconciliation processes, manual review workflows, known data quality issues, and downstream system dependencies.
- **Map source schemas:** For each source, define field mappings to ASRE's canonical event model. Identify event type resolution rules (HL7 trigger codes, patient class mappings, claims-specific logic).
- **Build facility alias file:** Compile known facility names, abbreviations, NPI numbers, CCN numbers, and legacy identifiers into the facility alias configuration.

### Phase 2: Configuration and Baseline (Weeks 3--4)

- **Deploy ASRE** in the customer's controlled environment (warehouse-native or containerized).
- **Configure pipeline parameters:** Stitching time windows, deduplication tolerance, source priority rankings, confidence scoring weights, and quality thresholds---tuned to the organization's source mix and operational context.
- **Run initial full-mode processing** to establish baseline quality metrics across the historical dataset.
- **Review baseline report:** Analyze duplicate rate, missing discharge rate, facility resolution rate, and confidence score distribution. Adjust thresholds and weights based on findings.

### Phase 3: Validation and Tuning (Weeks 5--6)

- **Validate output** against known-good encounters through manual spot checks and comparison to existing reconciled data.
- **Tune facility matching:** Review unresolved facility flags, add aliases, and adjust the fuzzy matching threshold if the precision/recall tradeoff needs rebalancing.
- **Tune confidence scoring:** Adjust signal weights and penalty values to reflect the organization's source trust hierarchy. For example, an organization with highly reliable ADT feeds may weight the HAS_ADT_ADMIT signal higher than the default.
- **Configure quality alerting:** Set webhook endpoints, define block-on-fail conditions, and establish alert routing.

### Phase 4: Production and Monitoring (Ongoing)

- **Switch to incremental mode:** Process only new and updated events since the last run, using watermark-based filtering with configurable lookback buffers.
- **Monitor quality metrics:** Track metric trends across runs and investigate warn/fail conditions. The quality check stage provides per-run metrics with historical comparability.
- **Maintain facility registry:** Periodically review unresolved facilities and update alias mappings as new facilities or name variants are encountered.
- **Add new sources:** When new ADT vendors, claims clearinghouses, or authorization systems are onboarded, add a source configuration file. No pipeline code changes are required.

### Prerequisites

| Requirement | Detail |
|-------------|--------|
| Warehouse | Snowflake, BigQuery, or Redshift with read/write access to source and output schemas |
| Compute | Container runtime (ECS, Cloud Run, or equivalent) or dbt-compatible execution environment |
| Source data | Pre-parsed ADT, claims, and/or authorization tables in the warehouse |
| Configuration | YAML files defining source mappings, facility aliases, and pipeline parameters |
| Security | All processing within customer VPC; no external PHI transmission |

---

## 7. ROI Analysis

**The financial case for admission signal reliability rests on four value levers: reduced manual reconciliation labor, prevented revenue leakage, faster denial resolution, and improved downstream analytics accuracy.** The estimates below use conservative assumptions grounded in published industry data, modeled for a mid-size health system processing 100,000--250,000 encounters annually.

### Direct Cost Savings: Manual Reconciliation

At an industry-average cost of $100 per duplicate record resolved[^6] and a pre-ASRE duplicate rate of 10% across 100,000 annual encounters:

- **Before:** 10,000 duplicates at $100 each = $1,000,000/year in reconciliation cost
- **After** (duplicate rate reduced to <1%): 1,000 duplicates at $100 each = $100,000/year
- **Net savings: $900,000/year**

Actual reconciliation costs vary by organization, staffing model, and existing tooling. Organizations with higher labor costs or more complex source environments typically see greater savings.

### Revenue Leakage Prevention

Incomplete or conflicting encounter data contributes to claim denials. While not all denials are attributable to admission data quality, registration and eligibility issues---closely tied to admission signal accuracy---account for a material share. For the average hospital putting $4.9 million at risk from denials,[^10] even a conservative 10% reduction in denial-related revenue leakage yields:

- **$490,000/year in avoided revenue loss per hospital**

Organizations where a larger share of denials stem from registration, eligibility, or encounter data errors will see proportionally greater impact.

### Denial Rework Cost Reduction

Administrative cost per denied claim averaged $57.23 in 2023, up from $43.84 in 2022.[^19] For an organization processing 500,000 claims annually at an 11.8% initial denial rate:

- 59,000 denials at $57.23 each = $3,376,570 in annual rework cost
- A 15% reduction in encounter-data-attributable denials: **$506,000/year saved**

### Downstream Analytics Value

Reliable encounter data improves the accuracy of readmission rate calculations, length-of-stay metrics, care transition analytics, and value-based care quality measures. Inaccurate encounter data that inflates or deflates quality measures can result in material financial adjustments under CMS value-based programs. Organizations participating in the Medicare Shared Savings Program, BPCI Advanced, or commercial value-based arrangements have direct financial exposure to encounter data accuracy.

### Summary ROI Model

| Value Lever | Conservative Annual Estimate |
|-------------|------------------------------|
| Manual reconciliation reduction | $900,000 |
| Revenue leakage prevention | $490,000 |
| Denial rework cost reduction | $506,000 |
| **Total quantifiable savings** | **$1,896,000/year** |
| Downstream analytics accuracy | Material but organization-specific |

*Modeled for a mid-size health system processing 100,000--250,000 encounters annually. Larger organizations and those with more fragmented source environments will see proportionally greater returns.*

As one VP of data engineering noted: "We were spending more on manually reconciling admission data than most organizations spend on their entire data engineering team. Automating the reconciliation layer was the single highest-ROI infrastructure investment we made."

---

## 8. Conclusion and Call to Action

The admission signal reliability problem is structural, not incidental. As long as healthcare operates with multiple source systems generating conflicting versions of the same encounter, organizations will face duplicated records, unreconciled timestamps, unresolved facility identities, and the downstream consequences: denied claims, inaccurate analytics, wasted labor, and clinical risk.

The regulatory trajectory is clear. CMS-0057-F mandates five production interoperability APIs by January 2027.[^13] TEFCA participation is scaling rapidly, with 12,130+ organizations now live.[^14] The ONC's information blocking enforcement, effective since 2024 with civil penalties up to $1 million per violation, ensures that more data will flow.[^20] More data flowing through more channels makes the reconciliation problem more urgent, not less.

ASRE addresses this problem at the infrastructure layer---not as an analytics application or a workflow tool, but as the reliability engine that sits between raw source feeds and every downstream system that depends on encounter data. Its nine-stage pipeline, configurable per customer and deployable entirely within the customer's controlled environment, transforms fragmented signals into a scored, auditable, unified encounter table.

**For organizations evaluating their admission data reliability:**

1. **Quantify your current state.** Measure your duplicate rate, missing discharge rate, and the labor hours spent on manual encounter reconciliation. These metrics establish your baseline and your business case.

2. **Audit your source coverage.** Catalog every ADT feed, claims source, authorization system, and eligibility file that contributes admission signals. Identify which sources are integrated, which are siloed, and where conflicts are most frequent.

3. **Assess downstream impact.** Trace how encounter data quality affects your denial rates, quality measure calculations, care coordination workflows, and value-based care performance. The financial exposure is often larger than expected.

4. **Evaluate purpose-built reliability infrastructure.** General-purpose ETL pipelines and EHR integration engines were not designed for multi-source encounter reconciliation. Purpose-built solutions deliver faster time-to-value, better coverage of real-world edge cases, and ongoing quality measurement that generic approaches cannot match.

The $83 billion that the healthcare industry spends annually on administrative transactions between providers and health plans[^21] represents an enormous surface area for improvement. Admission signal reliability is not the entire problem---but it is a foundational layer without which downstream efficiency gains are built on unreliable data.

---

## 9. References

[^1]: Industry estimates based on HL7 message volume analyses. Invene, "HL7 Standards Guide," 2024; Interfaceware, "HL7 Message Volume Analysis," 2024.

[^2]: Centers for Medicare & Medicaid Services. "Admission, Discharge, and Transfer Patient Event Notification Conditions of Participation." 42 CFR 482.24(d), 482.61(f), 485.638(d). Effective May 1, 2021.

[^3]: HIMSS Analytics. "Provider Affiliated EHR Platform Analysis." Based on 571,045 providers across 4,023 hospitals. Referenced in Healthcare IT News, "Why EHR Data Interoperability Is Such a Mess in 3 Charts."

[^4]: InterSystems. "Success with Healthcare Data Integration at Scale." InterSystems case study.

[^5]: U.S. Department of Health and Human Services, Office of the Assistant Secretary for Planning and Evaluation (ASPE). "State All-Payer Claims Database Report." 2023. https://aspe.hhs.gov/sites/default/files/documents/a2add9e2d2e196f240357fee73cf3990/APCD-PCOR-Report-2023.pdf

[^6]: American Health Information Management Association (AHIMA). "Patient Identity Management Whitepaper." 2019. https://ahima.org/media/m1pldevh/ahima-pim-whitepaper.pdf. See also: Black Book Market Research, 2018.

[^7]: Office of the National Coordinator for Health Information Technology (ONC). "Patient Identification and Matching Final Report." February 2014. https://www.healthit.gov/sites/default/files/resources/patient_identification_matching_final_report.pdf

[^8]: Pew Charitable Trusts. "Enhanced Patient Matching Is Critical to Achieving Full Promise of Digital Health Records." October 2018. https://www.pewtrusts.org/en/research-and-analysis/reports/2018/10/02/enhanced-patient-matching-critical-to-achieving-full-promise-of-digital-health-records

[^9]: Khare, R., et al. "Digital Health Data Quality Issues: Systematic Review." Journal of Medical Internet Research, 2023. PMC10131725. https://pmc.ncbi.nlm.nih.gov/articles/PMC10131725/

[^10]: Change Healthcare (now Optum). "Analysis of $262 Billion in Medical Claims Initially Denied." Healthcare Finance News, 2017. Based on 2016 claims data from 724 hospitals representing $1.8 trillion in transactions. https://www.healthcarefinancenews.com/news/change-healthcare-analysis-shows-262-million-medical-claims-initially-denied-meaning-billions. Denial rates have continued to rise: AHA reports 15.7% average initial denial rate for Medicare Advantage as of 2024.

[^11]: AHIMA Journal. "Cost to Rework Denied Claims." Range of $25--$181 per claim depending on complexity and appeal level.

[^12]: American Hospital Association (AHA). "Payer Denial Tactics: How to Confront a $20 Billion Problem." AHA Center for Health Innovation, April 2024. https://www.aha.org/aha-center-health-innovation-market-scan/2024-04-02-payer-denial-tactics-how-confront-20-billion-problem

[^13]: Centers for Medicare & Medicaid Services. "Medicare and Medicaid Programs; Advancing Interoperability and Improving Prior Authorization Processes (CMS-0057-F)." Federal Register, February 8, 2024. Document 2024-00895. https://www.cms.gov/cms-interoperability-and-prior-authorization-final-rule-cms-0057-f

[^14]: Sequoia Project / Recognized Coordinating Entity. "TEFCA Participation Statistics." Late 2025. https://rce.sequoiaproject.org/. See also: HealthIT.gov, "TEFCA Priorities and Plans for 2025."

[^15]: Office of the National Coordinator for Health Information Technology (ONC). "Non-Federal Acute Care Hospital EHR Adoption." 96% adoption of certified EHRs by 2021. https://healthit.gov/data/quickstats/non-federal-acute-care-hospital-electronic-health-record-adoption/

[^16]: Duplicate medical records survey, Twin Cities healthcare organizations. PMC2815491. https://pmc.ncbi.nlm.nih.gov/articles/PMC2815491/

[^17]: Office of the National Coordinator for Health Information Technology (ONC). "Interoperable Exchange of Patient Health Information among U.S. Hospitals, 2023." HealthIT.gov Data Briefs. https://www.healthit.gov/data/data-briefs/interoperable-exchange-patient-health-information-among-us-hospitals-2023

[^18]: HCI Innovation Group. "2025 Survey of Health Information Organizations: TEFCA Participation." 2025.

[^19]: Premier, Inc. "Administrative Cost per Denied Claim Analysis." 2023 data. Referenced in industry compilations.

[^20]: Office of the National Coordinator for Health Information Technology (ONC). "Information Blocking Enforcement." Civil monetary penalties up to $1 million per violation for health IT developers and networks; provider disincentives effective July 31, 2024. https://www.healthit.gov/topic/information-blocking/enforcement-alert

[^21]: CAQH. "2024 CAQH Index: Automating Healthcare Administrative Transactions." https://www.caqh.org/insights/caqh-index-report

**Additional references:**

- Harron, K., et al. "Evaluating Bias Due to Data Linkage Error in Electronic Healthcare Records." *BMC Medical Research Methodology*, 14:36, 2014. https://bmcmedresmethodol.biomedcentral.com/articles/10.1186/1471-2288-14-36

- Weiskopf, N.G., and Weng, C. "Methods and Dimensions of Electronic Health Record Data Quality Assessment: Enabling Reuse for Clinical Research." *Journal of the American Medical Informatics Association*, 20(1), 144--151, 2013. https://academic.oup.com/jamia/article/20/1/144/2909176

- Black Book Market Research. "2025 Revenue Cycle Leaders Confront Growing Financial Risks." Newswire, June 2025. https://www.newswire.com/news/2025-revenue-cycle-leaders-confront-growing-financial-risks-from-22598144

---

*ASRE is healthcare data reliability infrastructure. It is not an EHR replacement, a billing or claims adjudication system, or a business intelligence analytics platform. ASRE is the reliability layer between raw source feeds and the downstream analytics, operational, and financial systems that depend on trustworthy encounter data.*
