export const BRAND = {
  name: "ASRE",
  fullName: "Admission Signal Reliability Engine",
  tagline: "One Trusted Encounter Layer",
  description:
    "ASRE ingests fragmented ADT, claims, authorization, and eligibility signals and produces a single trusted output: a stitched, deduplicated, reconciled encounter table that healthcare operations can rely on.",
} as const;

export const NAV_LINKS = [
  { label: "Product", href: "#features" },
  { label: "Compare", href: "#compare" },
  { label: "Metrics", href: "#metrics" },
] as const;

export const CALENDLY_URL = "https://calendly.com/wbarakat94/30min";

export const HERO = {
  headline: "One Trusted Encounter Layer",
  highlightedPhrase: "Trusted Encounter",
  subheadline:
    "ASRE combines ADT, claims, authorization, and eligibility data into one encounter table with confidence scores and audit history.",
  ctaPrimary: "Book a Call",
  ctaSecondary: "Read the Whitepaper",
  whitepaperUrl: "/whitepaper.pdf",
} as const;

export const PAIN_POINTS = [
  {
    title: "Source Inputs",
    description:
      "Reads ADT, claims, authorization, and eligibility records from your warehouse tables.",
    stat: "4",
    statLabel: "source types",
  },
  {
    title: "Encounter Processing",
    description:
      "Runs canonicalize, facility matching, stitching, deduplication, reconciliation, scoring, and quality checks.",
    stat: "9",
    statLabel: "encounter stages",
  },
  {
    title: "Episode Processing",
    description:
      "Links encounters into episodes and computes episode quality metrics.",
    stat: "3",
    statLabel: "episode stages",
  },
  {
    title: "Output Model",
    description:
      "Writes unified encounters, detail, episodes, facility registry, quality metrics, run metrics, and audit logs.",
    stat: "7",
    statLabel: "output tables",
  },
] as const;

export const VALUE_METRICS = [
  {
    value: "~8 hrs/wk",
    label: "Time saved per analyst",
    detail: "Less manual cross-checking across ADT, claims, and authorization data.",
  },
  {
    value: "~20%",
    label: "Higher encounter accuracy",
    detail: "Fewer mismatched admits and discharges after reconciliation.",
  },
  {
    value: "~80%",
    label: "Fewer duplicate events",
    detail: "Duplicate signals are removed before they hit downstream reporting.",
  },
  {
    value: "~50%",
    label: "Less manual QA",
    detail: "Teams review flagged exceptions instead of reviewing every encounter.",
  },
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
    { label: "Documentation", href: "https://asre-docs.vercel.app" },
    { label: "GitHub", href: "https://github.com/wbarakat/asre" },
    { label: "Privacy", href: "/privacy" },
    { label: "Terms", href: "/terms" },
  ],
} as const;
