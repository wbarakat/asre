import fs from "fs";
import path from "path";
import matter from "gray-matter";

const CONTENT_DIR = path.join(process.cwd(), "content");

export interface DocMeta {
  title: string;
  description: string;
}

export interface Doc {
  meta: DocMeta;
  content: string; // raw MDX without frontmatter
}

/**
 * Given a slug array (e.g. ["getting-started", "overview"]),
 * read the corresponding .mdx file and return frontmatter + raw content.
 */
export function getDoc(slugParts: string[]): Doc {
  const relativePath =
    slugParts.length === 0 ? "index.mdx" : slugParts.join("/") + ".mdx";
  const fullPath = path.join(CONTENT_DIR, relativePath);

  if (!fs.existsSync(fullPath)) {
    throw new Error(`Doc not found: ${fullPath}`);
  }

  const raw = fs.readFileSync(fullPath, "utf-8");
  const { data, content } = matter(raw);

  return {
    meta: {
      title: (data.title as string) || "ASRE Docs",
      description: (data.description as string) || "",
    },
    content,
  };
}
