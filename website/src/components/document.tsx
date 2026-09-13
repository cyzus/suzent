import Link from "next/link";
import {
  DocsPage,
  DocsTitle,
  DocsDescription,
  DocsBody,
} from "fumadocs-ui/layouts/docs/page";
import { pages, type Page } from "@/lib/content";
import { messages } from "@/lib/messages";
import { Markdown } from "./markdown";
import { DocumentationLayout } from "./docs-layout";

export function Document({ page }: { page: Page }) {
  const text = messages(page.locale);
  const children = pages.filter(
    (p) =>
      p.locale === page.locale &&
      ((p.kind === "doc" &&
        p.relative?.split("/").slice(0, -1).join("/") === page.directory) ||
        (p.kind === "category" &&
          p.directory?.split("/").slice(0, -1).join("/") === page.directory)),
  );
  return (
    <DocumentationLayout locale={page.locale} currentUrl={page.url}>
      <DocsPage toc={page.toc ?? []} tableOfContent={{ style: "clerk" }}>
        <div className="eyebrow">{text.handbook}</div>
        <DocsTitle>{page.title}</DocsTitle>
        {page.description && (
          <DocsDescription>{page.description}</DocsDescription>
        )}
        {page.locale === "zh-Hans" &&
          !page.translated &&
          page.kind === "doc" && (
            <p className="translation-note">{text.fallback}</p>
          )}
        <DocsBody>
          {page.content ? (
            <div lang={page.translated ? page.locale : "en"}>
              <Markdown content={page.content} />
            </div>
          ) : (
            <div className="document-grid">
              {children.map((child) => (
                <Link
                  className="document-card"
                  key={child.url}
                  href={child.url}
                >
                  <strong>
                    {child.title} <span aria-hidden="true">↗</span>
                  </strong>
                  <p>{child.description}</p>
                </Link>
              ))}
            </div>
          )}
        </DocsBody>
        {page.source && (
          <a
            className="edit-link"
            href={
              "https://github.com/cyzus/suzent/edit/main/" +
              (page.translationSource || page.source)
            }
          >
            {text.edit}
          </a>
        )}
      </DocsPage>
    </DocumentationLayout>
  );
}
