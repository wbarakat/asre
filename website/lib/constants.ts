export const BRAND = {
  name: "ASRE",
  fullName: "Admission Signal Reliability Engine",
  tagline: "One Trusted Encounter Layer",
  description:
    "ASRE ingests fragmented ADT, claims, authorization, and eligibility signals and produces a single trusted output — a stitched, deduplicated, reconciled encounter table that healthcare operations can rely on.",
} as const;

export const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "Metrics", href: "#metrics" },
  { label: "About", href: "#about" },
] as const;

export const CALENDLY_URL = "https://calendly.com/wbarakat94/30min";

export const HERO = {
  headline: "One Trusted Encounter Layer",
  highlightedPhrase: "Trusted Encounter",
  subheadline:
    "Healthcare operations rely on fragmented admission signals scattered across ADT feeds, claims clearinghouses, and authorization portals. ASRE unifies them into a single, confidence-scored source of truth.",
  ctaPrimary: "Book a Call",
  ctaSecondary: "Read the Whitepaper",
  whitepaperUrl: "/whitepaper.pdf",
} as const;

export const PAIN_POINTS = [
  {
    title: "Fragmented Signals",
    description:
      "Admission data arrives from ADT feeds, claims, authorizations, and eligibility files — each with different schemas, timing, and reliability. No single source tells the whole story.",
    stat: "4+ sources",
    statLabel: "per encounter",
  },
  {
    title: "Manual Reconciliation",
    description:
      "Operations teams spend hours cross-referencing systems to determine whether a patient was actually admitted, when, and where. Error-prone and unscalable.",
    stat: "40%",
    statLabel: "time on manual matching",
  },
  {
    title: "Data Drift",
    description:
      "Source systems change schemas, add fields, and alter business rules without notice. Downstream analytics silently degrade, producing stale or incorrect encounter data.",
    stat: "Silent",
    statLabel: "failures compound",
  },
  {
    title: "Operational Risk",
    description:
      "Inaccurate admission data cascades into utilization review, discharge planning, and network adequacy — creating compliance exposure and revenue leakage.",
    stat: "$5.3T",
    statLabel: "US healthcare spending",
  },
] as const;

export const MARKET_STATS = [
  { value: 5.3, prefix: "$", suffix: "T", label: "US Healthcare Spending" },
  { value: 34.4, suffix: "M", label: "Annual Inpatient Admissions" },
  { value: 53, suffix: "M", label: "Prior Authorizations Annually" },
] as const;

export const PRODUCT_STATS = [
  { value: 9, suffix: "", label: "Pipeline Stages" },
  { value: 0.97, suffix: "", label: "Confidence Score Ceiling", decimals: 2 },
  { value: 93, suffix: "%", label: "Duplicate Reduction" },
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
  ],
} as const;
