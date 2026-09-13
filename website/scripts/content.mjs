import fs from "node:fs";
import path from "node:path";
import matter from "gray-matter";
import GithubSlugger from "github-slugger";
import yaml from "js-yaml";

export const site = "https://suzent.com";
export const root = path.resolve(import.meta.dirname, "..");
const repo = path.resolve(root, "..");
const docsRoot = path.join(repo, "docs");
const translations = path.join(
  root,
  "i18n/zh-Hans/docusaurus-plugin-content-docs/current",
);
export const locales = ["en", "zh-Hans"];
export const normalize = (url) => url.replace(/\/$/, "") || "/";
export const localize = (url, locale) =>
  locale === "en" ? url : `/zh-Hans${url === "/" ? "" : url}`;
export const kebab = (value) =>
  value
    .replace(/([a-z])([A-Z\d])/g, "$1-$2")
    .replace(/([\d])([a-z])/g, "$1-$2")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-|-$/g, "");
export function discover(dir) {
  return fs
    .readdirSync(dir, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name))
    .flatMap((entry) => {
      if (entry.name === "assets" || entry.name.startsWith(".")) return [];
      const full = path.join(dir, entry.name);
      return entry.isDirectory()
        ? discover(full)
        : /\.mdx?$/.test(entry.name)
          ? [full]
          : [];
    });
}
export function docUrl(relative, slug) {
  if (slug) return normalize("/docs/" + String(slug).replace(/^\//, ""));
  const parts = relative
    .replace(/\.mdx?$/, "")
    .split("/")
    .map((p) => p.replace(/^\d+-/, ""));
  const last = parts.at(-1);
  if (/^(readme|index)$/i.test(last) || last === parts.at(-2)) parts.pop();
  return normalize("/docs/" + parts.join("/"));
}
function read(file) {
  const { data, content } = matter(fs.readFileSync(file, "utf8"));
  const title =
    data.title || content.match(/^# (.+)$/m)?.[1] || path.basename(file, ".md");
  return { data, content, title };
}
function outsideFences(text, transform) {
  let fence = "";
  return text
    .split("\n")
    .map((line) => {
      const match = line.match(/^\s*(`{3,}|~{3,})/);
      if (match) {
        if (!fence) fence = match[1];
        else if (fence[0] === match[1][0] && match[1].length >= fence.length)
          fence = "";
        return line;
      }
      return fence ? line : transform(line);
    })
    .join("\n");
}
export function tableOfContents(content) {
  const slugger = new GithubSlugger();
  const toc = [];
  outsideFences(content, (line) => {
    const h = line.match(/^(#{2,6}) (.+)$/);
    if (h) {
      const title = h[2]
        .replace(/`([^`]+)`/g, "$1")
        .replace(/\*\*([^*]+)\*\*/g, "$1");
      toc.push({
        title,
        url: "#" + slugger.slug(title),
        depth: h[1].length,
      });
    }
    return line;
  });
  return toc;
}
export function createContent() {
  const files = discover(docsRoot);
  const translated = new Map(
    discover(translations).map((file) => [
      docUrl(path.relative(translations, file), read(file).data.slug),
      file,
    ]),
  );
  const docs = files
    .map((file) => {
      const { data, content, title } = read(file);
      return {
        kind: "doc",
        url: docUrl(path.relative(docsRoot, file), data.slug),
        file,
        source: path.relative(repo, file),
        relative: path.relative(docsRoot, file),
        title,
        content,
        description: data.description || "",
        position: data.sidebar_position ?? 999,
        draft: !!data.draft,
      };
    })
    .filter((doc) => !doc.draft);
  const docsByFile = new Map(docs.map((doc) => [doc.file, doc]));
  const docsByUrl = new Map(docs.map((doc) => [doc.url, doc]));
  const categories = [];
  const seen = new Set();
  for (const doc of docs) {
    let dir = path.dirname(doc.file);
    while (dir !== docsRoot && dir.startsWith(docsRoot)) {
      if (!seen.has(dir)) {
        seen.add(dir);
        const file = path.join(dir, "_category_.json");
        const data = fs.existsSync(file)
          ? JSON.parse(fs.readFileSync(file, "utf8"))
          : {};
        const title =
          data.label ||
          path.basename(dir).replace(/^\d+-/, "").replaceAll("-", " ");
        categories.push({
          kind: "category",
          url:
            "/docs/category/" +
            (title === "GitHub Sync" ? "github-sync" : kebab(title)),
          title,
          description: data.link?.description || "",
          directory: path.relative(docsRoot, dir),
          position: data.position ?? 999,
        });
      }
      dir = path.dirname(dir);
    }
  }
  const categoryTranslations = JSON.parse(
    fs.readFileSync(
      path.join(
        root,
        "i18n/zh-Hans/docusaurus-plugin-content-docs/current.json",
      ),
      "utf8",
    ),
  );
  const posts = discover(path.join(root, "blog"))
    .map((file) => {
      const { data, content, title } = read(file);
      const date = new Date(
        data.date || path.basename(file).slice(0, 10),
      ).toISOString();
      return {
        kind: "post",
        url:
          "/blog/" +
          (data.slug ||
            path
              .basename(file)
              .replace(/^\d{4}-\d\d-\d\d-/, "")
              .replace(/\.mdx?$/, "")),
        title,
        description: data.description || "",
        date,
        tags: data.tags || [],
        authors: Array.isArray(data.authors)
          ? data.authors
          : [data.authors || "suzent"],
        content,
        file,
        source: path.relative(repo, file),
      };
    })
    .sort((a, b) => b.date.localeCompare(a.date));
  const authors = yaml.load(
    fs.readFileSync(path.join(root, "blog/authors.yml"), "utf8"),
  );
  const tags = [...new Set(posts.flatMap((post) => post.tags))];
  const collections = [
    { kind: "blog", url: "/blog", title: "Blog" },
    { kind: "archive", url: "/blog/archive", title: "Archive" },
    { kind: "tags", url: "/blog/tags", title: "Tags" },
    { kind: "authors", url: "/blog/authors", title: "Authors" },
    ...tags.map((tag) => ({
      kind: "tag",
      url: "/blog/tags/" + kebab(tag),
      title: tag,
      tag,
    })),
    ...Object.entries(authors).map(([id, author]) => ({
      kind: "author",
      url: "/blog/authors/" + id,
      title: author.name,
      author: id,
    })),
  ];
  const privacyFile = path.join(root, "content/browser-privacy.md");
  const privacy = read(privacyFile);
  const other = [
    {
      kind: "home",
      url: "/",
      title: "The Sovereign AI Agent",
      description:
        "A sovereign AI agent whose identity, memory, skills, workspace, and runtime remain under your control—independent of any model or platform.",
    },
    {
      kind: "sovereign",
      url: "/sovereign",
      title: "What Is a Sovereign AI Agent?",
      description:
        "The four conditions of agent sovereignty and a five-question ownership test.",
    },
    {
      kind: "privacy",
      url: "/browser-privacy",
      file: privacyFile,
      source: "website/content/browser-privacy.md",
      title: privacy.title,
      description: privacy.data.description,
      content: privacy.content,
    },
    { kind: "notfound", url: "/404", title: "Page not found" },
  ];
  const all = [...docs, ...categories, ...posts, ...collections, ...other];
  const urls = new Set(all.map((p) => p.url));
  const unresolved = [];
  function resolveTarget(target, doc, isImage = false) {
    if (/^(https?:|mailto:|tel:|data:|#)/i.test(target)) {
      if (target.startsWith(site + "/")) {
        const u = new URL(target);
        if (urls.has(normalize(u.pathname))) {
          const translatedFile = translated.get(normalize(u.pathname));
          const lacksSection =
            doc.locale === "zh-Hans" &&
            u.hash &&
            translatedFile &&
            !tableOfContents(read(translatedFile).content).some(
              (heading) => heading.url === u.hash,
            );
          if (lacksSection) return u.pathname + u.search + u.hash;
          return (
            localize(normalize(u.pathname), doc.locale) + u.search + u.hash
          );
        }
      }
      return target;
    }
    const match = target.match(/^([^?#]*)(.*)$/);
    const raw = decodeURI(match[1]);
    const suffix = match[2];
    if (raw.startsWith("/zh-Hans/")) return target;
    if (raw.startsWith("/")) {
      if (urls.has(normalize(raw)))
        return localize(normalize(raw), doc.locale) + suffix;
      if (raw.startsWith("/img/") || raw.startsWith("/assets/")) return target;
    }
    const sourceFile = path.resolve(path.dirname(doc.file), raw);
    if (isImage && fs.existsSync(sourceFile)) {
      const rel = path.relative(repo, sourceFile);
      if (rel.startsWith(".."))
        throw new Error("Image outside repository: " + sourceFile);
      return "/content-assets/" + rel + suffix;
    }
    const candidate =
      docsByFile.get(sourceFile) ||
      docsByFile.get(sourceFile + ".md") ||
      docsByFile.get(path.join(sourceFile, "README.md"));
    if (candidate) return localize(candidate.url, doc.locale) + suffix;
    const isIndex =
      doc.relative &&
      /\/(README|index|[^/]+)\.md$/.test(doc.relative) &&
      docUrl(doc.relative) ===
        docUrl(path.dirname(doc.relative) + "/README.md");
    const base = site + doc.url + (isIndex ? "/" : "");
    const candidateUrl = normalize(new URL(raw, base).pathname);
    if (urls.has(candidateUrl))
      return localize(candidateUrl, doc.locale) + suffix;
    const sourceUrl = docUrl(path.relative(docsRoot, sourceFile));
    if (docsByUrl.has(sourceUrl))
      return localize(sourceUrl, doc.locale) + suffix;
    if (fs.existsSync(sourceFile) && sourceFile.startsWith(repo + "/"))
      return (
        "https://github.com/cyzus/suzent/blob/main/" +
        path.relative(repo, sourceFile) +
        suffix
      );
    unresolved.push({ source: doc.source, target });
    return target;
  }
  const pages = [];
  for (const locale of locales) {
    for (const original of all) {
      let doc = {
        ...original,
        locale,
        canonicalPath: original.url,
        url: localize(original.url, locale),
        translated: locale === "en",
      };
      if (locale === "zh-Hans" && original.kind === "doc") {
        const file = translated.get(original.url);
        if (file) {
          const tr = read(file);
          doc = {
            ...doc,
            title: tr.title,
            content: tr.content,
            description: tr.data.description || original.description,
            translated: true,
            translationSource: path.relative(repo, file),
          };
        }
      }
      if (locale === "zh-Hans" && original.kind === "category")
        doc.title =
          categoryTranslations[
            "sidebar.tutorialSidebar.category." + original.title
          ]?.message || original.title;
      if (doc.content) {
        const sourceDoc = { ...doc, url: original.url };
        let removedTitle = false;
        doc.content = outsideFences(doc.content, (line) => {
          if (/^import (Tabs|TabItem) from '@theme\//.test(line)) return "";
          if (!removedTitle && /^# /.test(line)) {
            removedTitle = true;
            return "";
          }
          if (line === "<!-- truncate -->") return "";
          return line.replace(
            /(!?\[[^\]]*\])\(<?([^\s)<>]+)>?(\s+"[^"]*")?\)/g,
            (_, label, target, title = "") =>
              `${label}(${resolveTarget(target, sourceDoc, label.startsWith("!"))}${title})`,
          );
        });
        doc.content = doc.content.replace(
          /:::([a-z]+)([^\n]*)\n([\s\S]*?)\n:::/g,
          (_, kind, title, body) =>
            `<Callout type="${kind === "warning" || kind === "danger" ? "warn" : "info"}" title="${title.trim() || kind}">\n\n${body}\n\n</Callout>`,
        );
        doc.toc = tableOfContents(doc.content);
        doc.searchText = doc.content
          .replace(/```[^\n]*\n/g, "\n")
          .replace(/<[^>]+>/g, " ")
          .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
          .replace(/[#*`|]/g, " ")
          .replace(/\s+/g, " ")
          .trim();
        if (!doc.description) doc.description = doc.searchText.slice(0, 180);
      }
      delete doc.file;
      pages.push(doc);
    }
  }
  if (unresolved.length)
    throw new Error(
      "Unresolved links:\n" + JSON.stringify(unresolved, null, 2),
    );
  const duplicates = pages.filter(
    (p, i) => pages.findIndex((other) => other.url === p.url) !== i,
  );
  if (duplicates.length)
    throw new Error("Duplicate routes: " + duplicates.map((p) => p.url));
  return { pages, authors };
}
