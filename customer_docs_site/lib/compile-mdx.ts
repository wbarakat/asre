import { compile } from "@mdx-js/mdx";
import remarkGfm from "remark-gfm";

/**
 * Compile raw MDX source to a JavaScript string at build time.
 * The resulting code can be evaluated on the client with `run()` from @mdx-js/mdx.
 */
export async function compileMdx(source: string): Promise<string> {
  const result = await compile(source, {
    outputFormat: "function-body",
    remarkPlugins: [remarkGfm],
  });
  return String(result);
}
