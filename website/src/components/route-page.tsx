import { DocRedirect } from "@/components/doc-redirect";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { pages, getPage } from "@/lib/content";
import { localePath } from "@/lib/locales";
import { messages } from "@/lib/messages";
import Home from "@/components/landing/Home";
import Sovereign, { COPY } from "@/components/sovereign/Sovereign";
import { Document } from "@/components/document";
import { Blog } from "@/components/blog";
import { Markdown } from "@/components/markdown";
import { SiteNav } from "@/components/site-nav";
import { SiteFooter } from "@/components/site-footer";
import zh from "../../i18n/zh-Hans/code.json";
type Props = { params: Promise<{ path?: string[] }> };
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const page = getPage("/" + ((await params).path ?? []).join("/"));
  if (!page) return {};
  const isZh = page.locale === "zh-Hans";
  const title =
    page.kind === "sovereign"
      ? COPY[page.locale].metaTitle
      : page.kind === "home" && isZh
        ? zh["homepage.meta.title"].message
        : page.title;
  const description =
    page.kind === "sovereign"
      ? COPY[page.locale].metaDescription
      : page.kind === "home" && isZh
        ? zh["homepage.meta.description"].message
        : page.description;
  const canonical = page.redirectTo?.split("#")[0] ?? (page.url === "/" ? "/" : page.url + "/");
  return {
    title,
    description,
    alternates: {
      canonical,
      languages: {
        en: localePath(canonical, "en"),
        "zh-Hans": localePath(canonical, "zh-Hans"),
        "x-default": localePath(canonical, "en"),
      },
      ...(page.kind.startsWith("blog")
        ? {
            types: {
              "application/rss+xml": localePath("/blog/rss.xml", page.locale),
            },
          }
        : {}),
    },
    openGraph: {
      title,
      description,
      url: canonical,
      locale: isZh ? "zh_CN" : "en_US",
      type: page.kind === "post" ? "article" : "website",
    },
    twitter: { title, description },
    ...((page.kind === "notfound" || page.kind === "redirect")
      ? { robots: { index: false, follow: true } }
      : {}),
  };
}
export default async function Page({ params }: Props) {
  const page = getPage("/" + ((await params).path ?? []).join("/"));
  if (!page) notFound();
  if (page.kind === "redirect") return <DocRedirect target={page.redirectTo!} />;
  const text = messages(page.locale);
  if (page.kind === "home") return <Home />;
  if (page.kind === "sovereign")
    return (
      <>
        <Sovereign locale={page.locale} />
        <SiteFooter locale={page.locale} />
      </>
    );
  if (page.kind === "doc" || page.kind === "category")
    return <Document page={page} />;
  if (page.kind === "privacy")
    return (
      <>
        <SiteNav />
        <main className="editorial">
          <h1>{page.title}</h1>
          {page.locale === "zh-Hans" && (
            <p className="translation-note">{text.fallback}</p>
          )}
          <article className="prose" lang="en">
            <Markdown content={page.content!} />
          </article>
        </main>
        <SiteFooter locale={page.locale} />
      </>
    );
  if (page.kind === "notfound")
    return (
      <>
        <SiteNav />
        <main className="editorial">
          <h1>404</h1>
          <p>{text.notFound}</p>
          <Link href={localePath("/", page.locale)}>{text.home} →</Link>
        </main>
      </>
    );
  return <Blog page={page} />;
}
