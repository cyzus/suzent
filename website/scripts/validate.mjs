import fs from "node:fs";
import path from "node:path";
import {
  createContent,
  root,
  normalize,
  localize,
  locales,
} from "./content.mjs";
const { pages } = createContent();
const output = path.join(root, "out");
const errors = [];
const legacy = JSON.parse(
  fs.readFileSync(path.join(root, "tests/legacy-routes.json"), "utf8"),
);
const pageByUrl = new Map(pages.map((p) => [p.url, p]));
for (const url of legacy)
  for (const locale of locales) {
    if (!pageByUrl.has(localize(url, locale)))
      errors.push("Missing legacy route: " + localize(url, locale));
  }
const decode = (value) =>
  value
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#x27;", "'")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">");
const htmlByUrl = new Map();
for (const page of pages) {
  const file = path.join(output, page.url, "index.html");
  if (!fs.existsSync(file)) {
    errors.push("Missing HTML: " + page.url);
    continue;
  }
  const html = fs.readFileSync(file, "utf8");
  htmlByUrl.set(page.url, html);
  if (!html.includes("<h1")) errors.push("Missing page heading: " + page.url);
  if (!html.includes(`lang="${page.locale}"`))
    errors.push("Missing locale: " + page.url);
  if (!html.includes('rel="canonical"'))
    errors.push("Missing canonical metadata: " + page.url);
}
for (const [url, html] of htmlByUrl) {
  for (const match of html.matchAll(
    /<(a|img|script|link)\b[^>]*?\b(href|src)="([^"]+)"/g,
  )) {
    const target = decode(match[3]);
    if (!target || /^(mailto:|tel:|data:|javascript:)/.test(target)) continue;
    const resolved = new URL(
      target,
      "https://suzent.com" + (url === "/" ? "/" : url + "/"),
    );
    if (resolved.origin !== "https://suzent.com") continue;
    const destination = normalize(decodeURI(resolved.pathname));
    if (htmlByUrl.has(destination)) {
      if (resolved.hash) {
        const id = decodeURIComponent(resolved.hash.slice(1));
        const targetHtml = htmlByUrl.get(destination);
        const ids = [...targetHtml.matchAll(/\bid="([^"]+)"/g)].map((m) =>
          decode(m[1]),
        );
        if (!ids.includes(id)) errors.push(`${url}: missing anchor ${target}`);
      }
    } else if (!fs.existsSync(path.join(output, decodeURI(resolved.pathname))))
      errors.push(`${url}: missing target ${target}`);
  }
}
for (const locale of locales) {
  const prefix = locale === "en" ? "" : locale + "/";
  for (const file of [
    "search-index.json",
    "blog/rss.xml",
    "blog/atom.xml",
    "blog/feed.json",
    "llms-full.txt",
  ])
    if (!fs.existsSync(path.join(output, prefix + file)))
      errors.push("Missing generated asset: " + prefix + file);
}
for (const locale of locales) {
  const quickstart = htmlByUrl.get(
    localize("/docs/getting-started/quickstart", locale),
  );
  if (
    !quickstart.includes('role="tablist"') ||
    !quickstart.includes("setup.ps1")
  )
    errors.push("Missing quickstart tab content: " + locale);
  const home = htmlByUrl.get(localize("/", locale));
  if (locale === "zh-Hans" && !home.includes("主权 AI 智能体"))
    errors.push("Missing Chinese landing translation");
  if (locale === "zh-Hans" && !quickstart.includes("本页内容"))
    errors.push("Missing Chinese docs UI translation");
  const prefix = locale === "en" ? "" : locale + "/";
  const index = JSON.parse(
    fs.readFileSync(path.join(output, prefix + "search-index.json"), "utf8"),
  );
  if (!index.some((entry) => entry.text.length > 5000))
    errors.push("Search index does not contain full documents: " + locale);
  const corpus = fs.readFileSync(
    path.join(output, prefix + "llms-full.txt"),
    "utf8",
  );
  if (!corpus.includes("sovereign"))
    errors.push("Missing sovereignty protocol in LLM corpus: " + locale);
}
if (errors.length) {
  console.error([...new Set(errors)].join("\n"));
  process.exit(1);
}
console.log(
  `Validated ${pages.length} pages, legacy route coverage, local links, anchors, assets, locale metadata, search indexes and feeds.`,
);
