import type { ReactNode } from "react";
import { Children, isValidElement } from "react";
import { MDXRemote } from "next-mdx-remote/rsc";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { rehypeCode } from "fumadocs-core/mdx-plugins";
import defaultComponents from "fumadocs-ui/mdx";
import { Tabs, Tab } from "fumadocs-ui/components/tabs";
import { Callout } from "fumadocs-ui/components/callout";
function ContentTabs({
  children,
  groupId,
}: {
  children: ReactNode;
  groupId?: string;
}) {
  const elements = Children.toArray(children).filter(isValidElement);
  const labels = elements.map(
    (element) => (element.props as { label: string }).label,
  );
  return (
    <Tabs items={labels} groupId={groupId}>
      {children}
    </Tabs>
  );
}
function TabItem({ label, children }: { label: string; children: ReactNode }) {
  return <Tab value={label}>{children}</Tab>;
}
export async function Markdown({ content }: { content: string }) {
  return (
    <MDXRemote
      source={content}
      components={{ ...defaultComponents, Tabs: ContentTabs, TabItem, Callout }}
      options={{
        mdxOptions: {
          remarkPlugins: [remarkGfm],
          rehypePlugins: [
            rehypeSlug,
            [
              rehypeCode,
              {
                themes: { light: "github-light", dark: "github-dark" },
                langs: [
                  "bash",
                  "shell",
                  "powershell",
                  "python",
                  "typescript",
                  "tsx",
                  "javascript",
                  "json",
                  "yaml",
                  "toml",
                  "dockerfile",
                  "text",
                  "sql",
                  "css",
                  "html",
                  "markdown",
                  "diff",
                  "xml",
                  "rust",
                ],
              },
            ],
          ],
        },
      }}
    />
  );
}
