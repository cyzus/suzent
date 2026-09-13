import Link from "next/link";
import { pages, authors, type Page } from "@/lib/content";
import { localePath } from "@/lib/locales";
import { messages } from "@/lib/messages";
import { SiteNav } from "./site-nav";
import { SiteFooter } from "./site-footer";
import { Markdown } from "./markdown";

export function Blog({ page }: { page: Page }) {
  const text = messages(page.locale);
  const posts = pages.filter(
    (p) =>
      p.kind === "post" &&
      p.locale === page.locale &&
      (!page.tag || p.tags?.includes(page.tag)) &&
      (!page.author || p.authors?.includes(page.author)),
  );
  const collectionTitles = {
    blog: text.blog,
    archive: text.archive,
    tags: text.tags,
    authors: text.authors,
  };
  const title =
    collectionTitles[page.kind as keyof typeof collectionTitles] ?? page.title;
  return (
    <>
      <SiteNav />
      <main className="editorial">
        <nav className="blog-nav">
          <Link href={localePath("/blog", page.locale)}>{text.allPosts}</Link>
          <Link href={localePath("/blog/archive", page.locale)}>
            {text.archive}
          </Link>
          <Link href={localePath("/blog/tags", page.locale)}>{text.tags}</Link>
          <Link href={localePath("/blog/authors", page.locale)}>
            {text.authors}
          </Link>
        </nav>
        <div className="eyebrow">SUZENT / {text.blog}</div>
        <h1>{title}</h1>
        {page.kind === "post" ? (
          <>
            <div className="article-meta">
              <time dateTime={page.date}>{page.date?.slice(0, 10)}</time>
              {page.authors?.map((id) => (
                <Link
                  key={id}
                  href={localePath("/blog/authors/" + id, page.locale)}
                >
                  {authors[id]?.name ?? id}
                </Link>
              ))}
            </div>
            {page.description && (
              <p className="article-description">{page.description}</p>
            )}
            {page.locale === "zh-Hans" && (
              <p className="translation-note">{text.fallback}</p>
            )}
            <article className="prose" lang="en">
              <Markdown content={page.content!} />
            </article>
            <div className="tag-list">
              {page.tags?.map((tag) => {
                const route = pages.find(
                  (p) =>
                    p.kind === "tag" &&
                    p.locale === page.locale &&
                    p.tag === tag,
                );
                return (
                  <Link key={tag} href={route!.url}>
                    {tag}
                  </Link>
                );
              })}
            </div>
            <script
              type="application/ld+json"
              dangerouslySetInnerHTML={{
                __html: JSON.stringify({
                  "@context": "https://schema.org",
                  "@type": "BlogPosting",
                  headline: page.title,
                  description: page.description,
                  datePublished: page.date,
                  author: page.authors?.map((id) => ({
                    "@type": "Organization",
                    name: authors[id]?.name,
                    url: authors[id]?.url,
                  })),
                  mainEntityOfPage: "https://suzent.com" + page.url,
                  image: "https://suzent.com/img/suzent-social-card.png",
                }).replace(/</g, "\u003c"),
              }}
            />
          </>
        ) : page.kind === "tags" ? (
          <div className="tag-list">
            {pages
              .filter((p) => p.kind === "tag" && p.locale === page.locale)
              .map((tag) => (
                <Link key={tag.url} href={tag.url}>
                  {tag.title} (
                  {posts.filter((p) => p.tags?.includes(tag.tag!)).length})
                </Link>
              ))}
          </div>
        ) : page.kind === "authors" ? (
          <div className="document-grid">
            {Object.entries(authors).map(([id, author]) => (
              <Link
                key={id}
                className="document-card"
                href={localePath("/blog/authors/" + id, page.locale)}
              >
                <strong>{author.name}</strong>
                <p>{author.title}</p>
              </Link>
            ))}
          </div>
        ) : (
          <div className="post-list">
            {posts.map((post) => (
              <article key={post.url}>
                <time dateTime={post.date}>{post.date?.slice(0, 10)}</time>
                <h2>
                  <Link href={post.url}>{post.title}</Link>
                </h2>
                <p>{post.description}</p>
                <Link className="read-more" href={post.url}>
                  {text.readMore} ↗
                </Link>
              </article>
            ))}
          </div>
        )}
      </main>
      <SiteFooter locale={page.locale} />
    </>
  );
}
