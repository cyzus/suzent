---
name: lint-skill
description: Health-check the notebook for contradictions, structural issues, hierarchy gaps, and knowledge decay.
---

# Lint Skill

A periodic editorial pass. Not just hygiene — lint surfaces new questions to investigate, resolves conflicting logic, and ensures knowledge does not silently decay.

---

## Step 1 — Read schema.md and index.md

Read `SCHEMA.md` from the notebook root first. The schema defines the vault's conventions
and what structure to expect.

Notebook root by execution mode:
- Sandbox Mode: `/mnt/notebook`
- Host Mode: `${MOUNT_NOTEBOOK}` (if mounted)

Then read `index.md` to understand what synthesized pages exist and how they are organized.

---

## Step 2 — Explore the vault

Run GlobTool broadly across the notebook. Many valuable pages exist outside `index.md`.
Get a full picture before checking for issues.

---

## Step 3 — Check for contradictions (ESCALATION)

Read related synthesized pages and check whether any claims conflict — within a page
or across related pages.

When a contradiction is found:
- Attempt to resolve it with the better-supported or more recent claim.
- **If uncertain or requires human judgment:** DO NOT just leave a silent warning. You must escalate it:
  1. Add a `> [!warning] Contradiction: [description]` callout in the specific markdown file.
  2. **Crucially:** Prepend a high-priority `[!alert] Contradiction found in [[path/page]]` to the top of `log.md` (or `index.md`) so the user sees it immediately for expert resolution.

---

## Step 4 — Check hierarchy and dependencies

Ensure the knowledge graph maintains connectivity.
- If an Entity page exists (e.g., `[[TimeQA Dataset]]`), it must link back to its parent category (e.g., `[[Datasets]]` or `[[Temporal Reasoning]]`).
- Avoid micro-islands. If a cluster of pages only links to each other but not to the rest of the vault, connect them to a higher-level Concept or Index.

---

## Step 5 — Check for broken links in index.md

For each entry in `index.md`, verify the linked file exists.
Fix broken paths or remove stale entries.

Check synthesized pages for wikilinks that use short names instead of full vault paths.
Fix dangling short-name links based on schema rules.

---

## Step 6 — Check for orphan synthesized pages

A synthesized page not in `index.md` and not linked from any other page is an orphan:
- Add to `index.md` if valuable.
- Add `## Related` links from other pages if the connection is meaningful.
- Delete only if truly obsolete.

---

## Step 7 — Check for missing reciprocal links

If page A links to page B in `## Related`, verify page B links back where appropriate.
Add missing reciprocal links.

---

## Step 8 — Check Status Decay

Examine the YAML frontmatter of Wiki/Syntheses pages.
- If a page has `status: active` but the `updated:` date is older than 90 days, the knowledge might be stale (especially in fast-moving fields like AI).
- Change its status to `needs-review` and log it so the user knows to re-evaluate the current state of the art.

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
Pages fixed: [[path/page]]
Gaps identified: {specific list}
```
