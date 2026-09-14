import test from "node:test";
import assert from "node:assert/strict";
import { createContent, docUrl, localize } from "../scripts/content.mjs";
const { pages } = createContent();

test("preserves folder-index and numeric-prefix URLs", () => {
  assert.equal(docUrl("02-concepts/tools/tools.md"), "/docs/concepts/tools");
  assert.equal(docUrl("02-concepts/memory/README.md"), "/docs/concepts/memory");
  assert.equal(docUrl("README.md"), "/docs");
  assert.equal(
    docUrl("01-getting-started/intro.md"),
    "/docs/getting-started/intro",
  );
  assert.equal(localize("/", "zh-Hans"), "/zh-Hans");
});
test("matches renamed Chinese files by published URL", () => {
  const page = pages.find((p) => p.url === "/zh-Hans/docs/concepts/providers");
  assert.equal(page.title, "提供商");
  assert.equal(page.translated, true);
  assert.match(page.translationSource, /providers\.md$/);
});
test("retains untranslated pages without claiming a translation", () => {
  const page = pages.find(
    (p) => p.url === "/zh-Hans/docs/concepts/providers/openai",
  );
  assert.equal(page.translated, false);
  assert.ok(page.content.length > 100);
});
test("does not remove imports or JSX inside code examples", () => {
  const page = pages.find((p) => p.url === "/docs/developing/development-guide");
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
  const tools = pages.find((p) => p.url === "/docs/concepts/tools");
  assert.ok(tools.toc.some((h) => h.url === "#web_search"));
  const skills = pages.find((p) => p.url === "/docs/concepts/skills");
  assert.ok(skills.toc.some((h) => h.url === "#step-3-add-resources-optional"));
  assert.ok(!skills.toc.some((h) => h.url === "#task-2-do-something-else"));
});
test("English section links stay usable when the translated page lacks that section", () => {
  const page = pages.find(
    (p) => p.url === "/zh-Hans/docs/concepts/memory/configuration",
  );
  assert.match(
    page.content,
    /\]\(\/docs\/concepts\/memory#memorymd-is-half-yours\)/,
  );
});


test("moved documentation has localized aliases and canonical targets", () => {
  for (const prefix of ["", "/zh-Hans"]) {
    for (const [from, to] of [
      ["/docs/developing/memory/architecture", "/docs/concepts/memory/architecture"],
      ["/docs/developing/memory/internals", "/docs/concepts/memory/internals"],
      ["/docs/developing/logo", "/docs/developing/development-guide#logo-standard"],
      ["/docs/developing/streaming-persistence-analysis", "/docs/developing/stream-recovery-protocol"],
    ]) {
      const alias = pages.find((p) => p.url === prefix + from);
      assert.equal(alias.kind, "redirect");
      assert.equal(alias.redirectTo, prefix + to);
      const [url, anchor] = alias.redirectTo.split("#");
      const target = pages.find((p) => p.url === url);
      assert.equal(target.kind, "doc");
      if (anchor) assert.ok(target.toc.some((h) => h.url === "#" + anchor));
    }
  }
  assert.ok(!pages.some((p) => /system-prompt-and-reminder-audit|docs-archive/.test(p.url)));
  assert.ok(!pages.some((p) => p.kind === "doc" && p.relative.startsWith("03-developing/memory/")));
});
