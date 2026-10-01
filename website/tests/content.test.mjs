import test from "node:test";
import assert from "node:assert/strict";
import { createContent, docUrl, localize } from "../scripts/content.mjs";
const { pages } = createContent();

test("preserves folder-index and numeric-prefix URLs", () => {
  assert.equal(docUrl("03-features/tools/tools.md"), "/docs/features/tools");
  assert.equal(docUrl("03-features/memory/README.md"), "/docs/features/memory");
  assert.equal(docUrl("README.md"), "/docs");
  assert.equal(
    docUrl("01-getting-started/intro.md"),
    "/docs/getting-started/intro",
  );
  assert.equal(localize("/", "zh-Hans"), "/zh-Hans");
});
test("matches Chinese files by published URL", () => {
  const page = pages.find((p) => p.url === "/zh-Hans/docs/models");
  assert.equal(page.title, "模型与提供商");
  assert.equal(page.translated, true);
  assert.match(page.translationSource, /04-models\/README\.md$/);
});
test("retains untranslated pages without claiming a translation", () => {
  const page = pages.find(
    (p) => p.url === "/zh-Hans/docs/features/automation",
  );
  assert.equal(page.translated, false);
  assert.ok(page.content.length > 100);
});
test("does not remove imports or JSX inside code examples", () => {
  const page = pages.find((p) => p.url === "/docs/developing/contributing/development-guide");
  assert.match(page.content, /import \{ SuzentLogo \}/);
  assert.match(page.content, /<SuzentLogo className/);
});
test("preserves quickstart commands and localizes relative navigation", () => {
  const page = pages.find(
    (p) => p.url === "/zh-Hans/docs/getting-started/quickstart",
  );
  assert.match(page.content, /setup\.ps1/);
  assert.match(page.content, /setup\.sh/);
  assert.doesNotMatch(page.content, /import Tabs from '@theme/);
  assert.match(page.content, /\/zh-Hans\/docs\/concepts\/providers/);
});
test("all documents have searchable full content and both locale routes", () => {
  for (const page of pages.filter(
    (p) => p.kind === "doc" && p.locale === "en",
  )) {
    assert.ok(page.searchText.length > 0, page.url);
    assert.ok(
      pages.some((p) => p.url === "/zh-Hans" + page.url),
      page.url,
    );
  }
});

test("headings retain code underscores and ignore nested code examples", () => {
  const tools = pages.find((p) => p.url === "/docs/developing/architecture/tool-system");
  assert.ok(tools.toc.some((h) => h.url === "#web_search"));
  const skills = pages.find((p) => p.url === "/docs/features/skills");
  assert.ok(skills.toc.some((h) => h.url === "#adding-skills"));
  assert.ok(!skills.toc.some((h) => h.url === "#checklist"));
});
test("English section links stay usable when the translated page lacks that section", () => {
  const page = pages.find(
    (p) => p.url === "/zh-Hans/docs/features/memory/configuration",
  );
  assert.match(
    page.content,
    /\]\(\/docs\/features\/memory#memorymd-is-half-yours\)/,
  );
});


