---
name: lint-skill
description: Health-check the notebook for contradictions, structural issues, hierarchy gaps, and knowledge decay.
---

# Lint Skill

A periodic editorial pass. Not just hygiene — lint surfaces new questions to investigate, resolves conflicting logic, and ensures knowledge does not silently decay.

---

## Step 1 — Read schema.md and index.md

Read `schema.md` from the notebook root first. Accept `SCHEMA.md` only when that is the
actual filename. The schema defines the vault's conventions and expected structure.

Notebook root by execution mode:
- Sandbox Mode: `/mnt/notebook`
- Host Mode: `${MOUNT_NOTEBOOK}` (if mounted)

Then read `index.md` to understand what synthesized pages exist and how they are organized.
If the schema enables the OKF-inspired profile, read `okf.md` before checking pages.

---

## Step 2 — Explore the vault

Run GlobTool broadly across the notebook. Many valuable pages exist outside `index.md`.
Get a full picture before checking for issues.

---

## Step 3 — Check for contradictions (ESCALATION)

Read related synthesized pages and check whether any claims conflict — within a page
or across related pages.

When a contradiction is found:
- Resolve it only when the evidence and the schema make the correct claim unambiguous.
- If human judgment is required, add a `> [!warning] Contradiction: [description]`
  callout to the affected page, append the issue to the current lint entry in `log.md`,
  and report it prominently to the user. Never prepend to an append-only log.

---

## Step 4 — Check hierarchy and dependencies

Ensure the knowledge graph maintains connectivity.
- If an Entity page exists (e.g., `[[TimeQA Dataset]]`), it must link back to its parent category (e.g., `[[Datasets]]` or `[[Temporal Reasoning]]`).
- Avoid micro-islands. If a cluster of pages only links to each other but not to the rest of the vault, connect them to a higher-level Concept or Index.

---

## Step 5 — Check for broken links in index.md

For each entry in `index.md`, verify the linked file exists.
Fix broken paths or remove stale entries.

Check synthesized pages for ambiguous or broken internal links and fix them according to the
schema's link rules.

---

## Step 6 — Check for orphan synthesized pages

A synthesized page not in `index.md` and not linked from any other page is an orphan:
- Add to `index.md` if valuable.
- Add `## Related` links from other pages if the connection is meaningful.
- Recommend deletion if truly obsolete; delete the page only when the user approves or
  the active schema explicitly authorizes automatic removal.

---

## Step 7 — Check for missing reciprocal links

If page A links to page B in `## Related`, verify page B links back where appropriate.
Add missing reciprocal links.

---

## Step 8 — Check Status Decay

Apply page-level `stale_after` dates and the fallback decay policy defined by `schema.md`.
Use its review marker; if it defines none, report candidates without changing frontmatter.

---

## Step 9 — Identify gaps

Look for:
- Topics recurring in recent daily logs with no synthesized coverage.
- Wikilinks in synthesized pages pointing to non-existent pages.
- Concepts appearing across multiple pages with no dedicated reference page.
- Synthesized pages with thin `## Overview` or lacking depth.

List gaps explicitly with specifics — they drive future ingest targets.

---

## Step 10 — Append to log.md

```
## [YYYY-MM-DD] lint
Issues found: {N} contradictions, {N} broken links, {N} missing cross-references
Decay flagged: {N} pages marked needs-review
Pages fixed: {schema-compliant page links}
Gaps identified: {specific list}
```
