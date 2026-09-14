import fs from "node:fs";
import path from "node:path";
import { createContent, root, site, locales } from "./content.mjs";
const content = createContent();
const sovereignty = JSON.parse(
  fs.readFileSync(path.join(root, "content/sovereignty.json"), "utf8"),
);

fs.mkdirSync(path.join(root, ".generated"), { recursive: true });
fs.writeFileSync(
  path.join(root, ".generated/content.json"),
  JSON.stringify(content),
);
fs.mkdirSync(path.join(root, "public"), { recursive: true });
fs.cpSync(path.join(root, "static"), path.join(root, "public"), {
  recursive: true,
});
fs.cpSync(
  path.join(root, "../docs/assets"),
  path.join(root, "public/content-assets/docs/assets"),
  {
    recursive: true,
    filter: (source) =>
      fs.statSync(source).isDirectory() ||
      /\.(png|jpg|jpeg|svg|webp|gif|avif)$/i.test(source),
  },
);
const xml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
const publicPath = (url) => path.join(root, "public", url);
const write = (url, text) => {
  const file = publicPath(url);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, text);
};
write(".nojekyll", "");
write(
  "sitemap.xml",
  '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' +
    content.pages
      .filter((p) => p.kind !== "notfound" && p.kind !== "redirect")
      .map(
        (p) =>
          `<url><loc>${site}${xml(p.url === "/" ? "/" : p.url + "/")}</loc></url>`,
      )
      .join("") +
    "</urlset>",
);
for (const locale of locales) {
  const prefix = locale === "en" ? "" : locale + "/";
  const pages = content.pages.filter((p) => p.locale === locale);
  write(
    prefix + "search-index.json",
    JSON.stringify(
      pages
        .filter((p) => p.content)
        .map((p) => ({ url: p.url, title: p.title, text: p.searchText })),
    ),
  );
  const docs = pages.filter((p) => p.kind === "doc");
  const copy = sovereignty[locale];
  const protocol = `# ${copy.metaTitle}\n\nSource: ${site}/${prefix}sovereign\n\n${copy.definition}\n\n${copy.disambiguation}\n\n${copy.pillars.map((p) => `## ${p.title}\n\n${p.description}\n\n${p.formula}`).join("\n\n")}\n\n${copy.tests.map((t) => `## ${t.question}\n\n${t.answer}`).join("\n\n")}`;
  write(
    prefix + "llms.txt",
    "# Suzent\n\n" +
      copy.definition +
      "\n\n" +
      `Full documentation: ${site}/${prefix}llms-full.txt\n\n` +
      pages
        .filter((p) => p.kind === "doc" || p.kind === "sovereign")
        .map((p) => `- [${p.title}](${site}${p.url})`)
        .join("\n") +
      "\n",
  );
  write(
    prefix + "llms-full.txt",
    "# Suzent: the sovereign AI agent\n\n" +
      protocol +
      "\n\n" +
      docs
        .map(
          (p) =>
            `---\n\n# ${p.title}\n\nSource: ${site}${p.url}\n\n${p.content.replace(/\]\(\//g, "](" + site + "/")}`,
        )
        .join("\n\n"),
  );
  const posts = pages.filter((p) => p.kind === "post");
  write(
    prefix + "blog/rss.xml",
    '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>Suzent</title><link>' +
      site +
      "/" +
      prefix +
      "blog/</link><description>Suzent updates</description>" +
      posts
        .map(
          (p) =>
            `<item><title>${xml(p.title)}</title><link>${site}${p.url}/</link><guid>${site}${p.url}/</guid><pubDate>${new Date(p.date).toUTCString()}</pubDate><description>${xml(p.description)}</description></item>`,
        )
        .join("") +
      "</channel></rss>",
  );
  write(
    prefix + "blog/atom.xml",
    '<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><id>' +
      site +
      "/" +
      prefix +
      "blog/</id><title>Suzent</title><updated>" +
      posts[0].date +
      "</updated>" +
      posts
        .map(
          (p) =>
            `<entry><id>${site}${p.url}/</id><title>${xml(p.title)}</title><link href="${site}${p.url}/"/><updated>${p.date}</updated><summary>${xml(p.description)}</summary></entry>`,
        )
        .join("") +
      "</feed>",
  );
  write(
    prefix + "blog/feed.json",
    JSON.stringify({
      version: "https://jsonfeed.org/version/1.1",
      title: "Suzent",
      home_page_url: site + "/" + prefix + "blog/",
      items: posts.map((p) => ({
        id: site + p.url,
        url: site + p.url,
        title: p.title,
        content_text: p.searchText,
        date_published: p.date,
      })),
    }),
  );
}
console.log(
  `Prepared ${content.pages.length} routes (${content.pages.filter((p) => p.kind === "doc").length} localized docs), search indexes, feeds, sitemap and LLM corpus.`,
);
