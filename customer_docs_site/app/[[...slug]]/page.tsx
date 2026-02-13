import { getDoc } from "@/lib/docs";
import { compileMdx } from "@/lib/compile-mdx";
import { getAllSlugs } from "@/lib/navigation";
import { MdxRenderer } from "@/components/mdx-renderer";
import type { Metadata } from "next";

interface PageProps {
  params: Promise<{ slug?: string[] }>;
}

export async function generateStaticParams() {
  return getAllSlugs().map((parts) => ({
    slug: parts.length === 0 ? undefined : parts,
  }));
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const slugParts = slug ?? [];
  const doc = getDoc(slugParts);
  return {
    title: `${doc.meta.title} - ASRE Docs`,
    description: doc.meta.description,
  };
}

export default async function DocPage({ params }: PageProps) {
  const { slug } = await params;
  const slugParts = slug ?? [];
  const doc = getDoc(slugParts);
  const compiled = await compileMdx(doc.content);

  return (
    <article>
      <MdxRenderer code={compiled} />
    </article>
  );
}
