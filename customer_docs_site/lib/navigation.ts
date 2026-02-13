export interface NavItem {
  title: string;
  slug: string;
}

export interface NavGroup {
  group: string;
  pages: NavItem[];
}

// Titles derived from frontmatter; slug matches the docs.json paths
export const navigation: NavGroup[] = [
  {
    group: "Getting Started",
    pages: [
      { title: "Introduction", slug: "" },
      { title: "Overview", slug: "getting-started/overview" },
      { title: "Installation", slug: "getting-started/installation" },
      { title: "Onboarding", slug: "getting-started/onboarding" },
    ],
  },
  {
    group: "Configuration",
    pages: [
      { title: "Overview", slug: "configuration/overview" },
      { title: "Warehouse", slug: "configuration/warehouse" },
      { title: "Sources", slug: "configuration/sources" },
      {
        title: "Facility Normalization",
        slug: "configuration/facility-normalization",
      },
      { title: "Quality & Alerting", slug: "configuration/quality-alerting" },
    ],
  },
  {
    group: "Pipelines",
    pages: [
      { title: "Overview", slug: "pipelines/overview" },
      { title: "Stages", slug: "pipelines/stages" },
      { title: "Episodes", slug: "pipelines/episodes" },
    ],
  },
  {
    group: "Operations",
    pages: [
      { title: "CLI Commands", slug: "operations/cli" },
      { title: "Run Modes", slug: "operations/run-modes" },
      { title: "Health Checks", slug: "operations/health" },
      { title: "Migrations", slug: "operations/migrations" },
      { title: "Troubleshooting", slug: "operations/troubleshooting" },
    ],
  },
  {
    group: "Data Model",
    pages: [{ title: "Output Tables", slug: "data-model/tables" }],
  },
];

/** Flat list of all valid slugs for generateStaticParams */
export function getAllSlugs(): string[][] {
  const slugs: string[][] = [[]]; // root = index
  for (const group of navigation) {
    for (const page of group.pages) {
      if (page.slug !== "") {
        slugs.push(page.slug.split("/"));
      }
    }
  }
  return slugs;
}
