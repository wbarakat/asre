export const BRAND = {
  name: "ASRE",
  fullName: "Admission Signal Reliability Engine",
  tagline: "One Trusted Encounter Layer",
  description:
    "ASRE ingests fragmented ADT, claims, authorization, and eligibility signals and produces a single trusted output: a stitched, deduplicated, reconciled encounter table that healthcare operations can rely on.",
} as const;

export const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "Compare", href: "#compare" },
  { label: "Metrics", href: "#metrics" },
] as const;

export const CALENDLY_URL = "https://calendly.com/wbarakat94/30min";

export const HERO = {
  headline: "One Trusted Encounter Layer",
  highlightedPhrase: "Trusted Encounter",
  subheadline:
    "Admission signals are scattered across ADT feeds, claims, and authorization portals. ASRE unifies them into a single, confidence-scored source of truth.",
  ctaPrimary: "Book a Call",
  ctaSecondary: "Read the Whitepaper",
  whitepaperUrl: "/whitepaper.pdf",
} as const;

export const PAIN_POINTS = [
  {
    title: "Fragmented Signals",
    description:
      "Every encounter touches 4+ systems with different schemas and timing. No single source tells the whole story.",
    stat: "4+",
    statLabel: "sources per encounter",
  },
  {
    title: "Manual Reconciliation",
    description:
      "Ops teams burn hours cross-referencing systems to confirm a patient was actually admitted, when, and where.",
    stat: "40%",
    statLabel: "time on manual matching",
  },
  {
    title: "Silent Data Drift",
    description:
      "Upstream schemas change without notice. Downstream analytics silently degrade until someone catches it.",
    stat: "3x",
    statLabel: "annual schema changes",
  },
  {
    title: "Revenue Leakage",
    description:
      "Bad admission data cascades into UR, discharge planning, and network adequacy. Missed encounters cost real dollars.",
    stat: "$17B",
    statLabel: "lost to denied claims yearly",
  },
] as const;

export const MARKET_STATS = [
  { value: 5.3, prefix: "$", suffix: "T", label: "US Healthcare Spending" },
  { value: 34.4, suffix: "M", label: "Annual Inpatient Admissions" },
  { value: 53, suffix: "M", label: "Prior Authorizations Annually" },
] as const;

export const PRODUCT_STATS = [
  { value: 12, suffix: "", label: "Pipeline Stages" },
  { value: 0.97, suffix: "", label: "Confidence Score Ceiling", decimals: 2 },
  { value: 93, suffix: "%", label: "Duplicate Reduction" },
] as const;

export const COMPARISON_ROWS = [
  {
    feature: "Encounter Stitching",
    detail: "Group events into encounters across sources",
    diy: "partial" as const,
    asre: "yes" as const,
  },
  {
    feature: "Facility Matching",
    detail: "Resolve variant names to canonical IDs",
    diy: "no" as const,
    asre: "yes" as const,
  },
  {
    feature: "Cross-Source Reconciliation",
    detail: "Resolve timestamp and classification conflicts",
    diy: "no" as const,
    asre: "yes" as const,
  },
  {
    feature: "Duplicate Detection",
    detail: "Configurable match fields with audit trail",
    diy: "partial" as const,
    asre: "yes" as const,
  },
  {
    feature: "Confidence Scoring",
    detail: "Weighted 0\u20131 score with explainable signals",
    diy: "no" as const,
    asre: "yes" as const,
  },
  {
    feature: "Episode Grouping",
    detail: "Readmissions, transfers, post-acute chains",
    diy: "no" as const,
    asre: "yes" as const,
  },
  {
    feature: "New Source Onboarding",
    detail: "Add a data source without code changes",
    diy: "no" as const,
    asre: "yes" as const,
  },
  {
    feature: "VPC-Only / No PHI Export",
    detail: "Data never leaves your infrastructure",
    diy: "yes" as const,
    asre: "yes" as const,
  },
] as const;

export const BOOK_CALL = {
  heading: "See ASRE in Action",
  description:
    "Schedule a 30-minute walkthrough to see how ASRE can unify your admission signals, eliminate manual reconciliation, and deliver confidence-scored encounter data to your operations team.",
} as const;

export const FOOTER = {
  copyright: `\u00A9 ${new Date().getFullYear()} ASRE. All rights reserved.`,
  links: [
    { label: "Whitepaper", href: "/whitepaper.pdf" },
    { label: "Documentation", href: "#" },
    { label: "GitHub", href: "#" },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
  ],
} as const;
