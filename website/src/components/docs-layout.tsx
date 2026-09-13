import type { ReactNode } from "react";
import Link from "next/link";
import { DocsLayout } from "fumadocs-ui/layouts/docs";
import type { Node } from "fumadocs-core/page-tree";
import { pages } from "@/lib/content";
import { localePath, type Locale } from "@/lib/locales";
import { messages } from "@/lib/messages";
import { Search } from "./search";

export function DocumentationLayout({
  children,
  locale,
  currentUrl,
}: {
  children: ReactNode;
  locale: Locale;
  currentUrl: string;
}) {
  const text = messages(locale);
  const docs = pages.filter((p) => p.locale === locale && p.kind === "doc");
  const categories = pages.filter(
    (p) => p.locale === locale && p.kind === "category",
  );
  function childrenOf(directory: string): Node[] {
    const folderNodes = categories
      .filter(
        (p) => p.directory?.split("/").slice(0, -1).join("/") === directory,
      )
      .map((category) => ({
        position: category.position ?? 999,
        node: {
          type: "folder" as const,
          name: category.title,
          index: {
            type: "page" as const,
            name: category.title,
            url: category.url,
          },
          children: childrenOf(category.directory!),
        },
      }));
    const docNodes = docs
      .filter(
        (p) => p.relative?.split("/").slice(0, -1).join("/") === directory,
      )
      .map((page) => ({
        position: page.position ?? 999,
        node: { type: "page" as const, name: page.title, url: page.url },
      }));
    return [...folderNodes, ...docNodes]
      .sort(
        (a, b) =>
          a.position - b.position ||
          String(a.node.name).localeCompare(String(b.node.name)),
      )
      .map((item) => item.node);
  }
  return (
    <DocsLayout
      tree={{ name: text.docs, children: childrenOf("") }}
      nav={{
        title: (
          <span className="brand">
            <img src="/img/logo.svg" width={26} height={26} alt="" />
            SUZENT <small>/ {text.docs}</small>
          </span>
        ),
        url: localePath("/", locale),
      }}
      links={[
        { text: text.home, url: localePath("/", locale) },
        { text: text.blog, url: localePath("/blog", locale) },
        {
          text: "GitHub",
          url: "https://github.com/cyzus/suzent",
          external: true,
        },
      ]}
      searchToggle={{ enabled: false }}
      sidebar={{
        defaultOpenLevel: 1,
        banner: <Search />,
        footer: (
          <div className="sidebar-note">
            <span className="status-dot" />
            {text.tagline}
            <Link
              aria-label={text.language}
              href={localePath(currentUrl, locale === "en" ? "zh-Hans" : "en")}
            >
              {locale === "en" ? "中文" : "EN"}
            </Link>
          </div>
        ),
      }}
    >
      {children}
    </DocsLayout>
  );
}
