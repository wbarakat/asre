"use client";

import * as runtime from "react/jsx-runtime";
import { run } from "@mdx-js/mdx";
import { useState, useEffect } from "react";
import type { MDXModule } from "mdx/types";
import { mintlifyComponents } from "./mintlify";

/**
 * Client component that takes a pre-compiled MDX function-body string
 * and renders it with our custom component map.
 */
export function MdxRenderer({ code }: { code: string }) {
  const [Content, setContent] = useState<MDXModule["default"] | null>(null);

  useEffect(() => {
    (async () => {
      const mod = await run(code, {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        ...(runtime as any),
        baseUrl: import.meta.url,
      });
      setContent(() => mod.default);
    })();
  }, [code]);

  if (!Content) {
    return null;
  }

  return <Content components={allComponents} />;
}

/* ------------------------------------------------------------------ */
/* Full component map: HTML overrides + Mintlify stubs                 */
/* ------------------------------------------------------------------ */

const allComponents = {
  h1: (props: React.ComponentProps<"h1">) => (
    <h1
      className="mb-4 mt-8 text-3xl font-bold tracking-tight text-white first:mt-0"
      {...props}
    />
  ),
  h2: (props: React.ComponentProps<"h2">) => (
    <h2
      className="mb-3 mt-8 text-2xl font-semibold tracking-tight text-white"
      {...props}
    />
  ),
  h3: (props: React.ComponentProps<"h3">) => (
    <h3
      className="mb-2 mt-6 text-xl font-semibold text-white"
      {...props}
    />
  ),
  h4: (props: React.ComponentProps<"h4">) => (
    <h4
      className="mb-2 mt-4 text-lg font-semibold text-white"
      {...props}
    />
  ),
  p: (props: React.ComponentProps<"p">) => (
    <p className="my-3 leading-7 text-zinc-300" {...props} />
  ),
  a: (props: React.ComponentProps<"a">) => (
    <a
      className="text-[#60A5FA] underline decoration-[#60A5FA]/30 underline-offset-2 hover:decoration-[#60A5FA]"
      {...props}
    />
  ),
  ul: (props: React.ComponentProps<"ul">) => (
    <ul className="my-3 ml-6 list-disc space-y-1 text-zinc-300" {...props} />
  ),
  ol: (props: React.ComponentProps<"ol">) => (
    <ol
      className="my-3 ml-6 list-decimal space-y-1 text-zinc-300"
      {...props}
    />
  ),
  li: (props: React.ComponentProps<"li">) => (
    <li className="leading-7" {...props} />
  ),
  strong: (props: React.ComponentProps<"strong">) => (
    <strong className="font-semibold text-white" {...props} />
  ),
  code: (props: React.ComponentProps<"code">) => {
    return (
      <code
        className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-sm text-[#60A5FA]"
        {...props}
      />
    );
  },
  pre: (props: React.ComponentProps<"pre">) => (
    <pre
      className="my-4 overflow-x-auto rounded-lg border border-zinc-700 bg-zinc-900 p-4 font-mono text-sm leading-6 text-zinc-300 [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-zinc-300"
      {...props}
    />
  ),
  table: (props: React.ComponentProps<"table">) => (
    <div className="my-4 overflow-x-auto">
      <table
        className="min-w-full border-collapse text-sm text-zinc-300"
        {...props}
      />
    </div>
  ),
  thead: (props: React.ComponentProps<"thead">) => (
    <thead className="border-b border-zinc-700" {...props} />
  ),
  th: (props: React.ComponentProps<"th">) => (
    <th
      className="px-3 py-2 text-left text-sm font-semibold text-white"
      {...props}
    />
  ),
  td: (props: React.ComponentProps<"td">) => (
    <td className="border-b border-zinc-800 px-3 py-2" {...props} />
  ),
  tr: (props: React.ComponentProps<"tr">) => (
    <tr className="border-b border-zinc-800 last:border-0" {...props} />
  ),
  hr: () => <hr className="my-8 border-zinc-700" />,
  blockquote: (props: React.ComponentProps<"blockquote">) => (
    <blockquote
      className="my-4 border-l-4 border-zinc-600 pl-4 italic text-zinc-400"
      {...props}
    />
  ),
  ...mintlifyComponents,
};
