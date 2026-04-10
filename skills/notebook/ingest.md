---
name: ingest-skill
description: Compile unprocessed raw sources into the notebook knowledge base, ensuring dynamic knowledge is separated from static project files.
---

# Ingest Skill

A deliberate synthesis operation. Read everything first. Think before writing.
Synthesize — do not transcribe.

---

## Step 1 — Read schema.md

Read `/mnt/notebook/SCHEMA.md` (or `schema.md`) completely before doing anything else.

The schema defines:
- The vault's folder structure (e.g., Projects vs. Wiki/Concepts).
- Where new synthesized pages should be placed.
- What page types and index categories to use.
- Any additional conventions specific to this vault.

Everything you do in subsequent steps must follow the schema.

---

## Step 2 — Identify unprocessed sources

Read `log.md` at the notebook root.

**Daily logs:** find the latest entry with prefix `## [...] ingest | daily logs`.
Extract the end date. Unprocessed = all `/shared/memory/YYYY-MM-DD.md` files newer than that date.

**Inbox files:** collect all filenames already listed under "Sources:" in any log entry.
Unprocessed = all files in `/mnt/notebook/inbox/` not already listed and not in `processed/`.

If nothing is unprocessed, report and stop.

---

## Step 3 — Explore the existing vault

Run GlobTool across the notebook to understand what already exists.
Read `index.md` to know what synthesized pages are already cataloged.

You cannot make good decisions about what to create or update without this picture.
A page created in ignorance of the vault will be a duplicate or an orphan.

---

## Step 4 — Read all unprocessed sources in full

Read every source completely before writing anything.

For daily logs, read for substance: what is the user working on, what decisions were made,
what problems were encountered, what topics appear repeatedly?

For inbox files: read the full document and note the main topics, key arguments, and named entities.

---

## Step 5 — Decide what to create or update

**CRITICAL: Separate Knowledge from Projects (Dynamic vs. Static)**
If a general concept is found within a specific project or document, **do not lock it inside the project folder**. Extract it into a global Wiki/Concepts page and link to it using `[[wikilinks]]`.

For each significant topic, ask:

**Does it already exist in the vault?**
If a folder or file already covers this topic, do not create a parallel page.
Update the existing file, add a new file inside the existing folder, or simply link to it.

**Is a new synthesized page warranted?**
Only create one if:
- It is a cross-cutting synthesis spanning multiple existing areas.
- It is a concept or comparison with no natural home in the vault.
- It is a summary of an ingested external document (Literature).
- The topic is significant and likely to recur.

**Where does it go?** Follow schema.md.

---

## Step 6 — Write or update pages

**MANDATORY FRONTMATTER:** Every compiled Wiki page must include YAML frontmatter:
```yaml
---
title: {Page Title}
type: concept | literature | synthesis | entity
status: active | superseded | needs-review
confidence: high | medium | speculative
updated: YYYY-MM-DD
---
```

**When processing Literature/Papers:**
Do not just write a generic summary. Extract specific dimensions:
- **Key Claims:** Falsifiable/core arguments.
- **Methodology/Innovations:** What is novel?
- **Contradictions:** How does this conflict with or support existing vault knowledge?

**Updating an existing page:**
- Read it fully first. Do not duplicate what is already there.
- Rewrite `## Overview` only if understanding has materially changed.
- Add to `## Related` using full vault paths.
- Add to `## Sources`, update `updated:` in frontmatter.

**Creating a new page:**
- Write a genuine `## Overview` paragraph — not a stub, not a list.
- Add `## Related` with full vault paths to related existing pages.

After writing all pages, check cross-references: if page A links to page B,
should page B link back? Add reciprocal `## Related` entries where meaningful.

---

## Step 7 — Update index.md

Add entries only for new synthesized pages you created.
Do not add existing vault pages that were merely updated.
Use the categories defined in schema.md. Update page count and date.
Write meaningful one-line summaries — not just the page title.

---

## Step 8 — Append to log.md

```
## [YYYY-MM-DD] ingest | {description}
Pages created: [[path/page]]
Pages updated: [[path/page]] (what changed)
Sources: {filenames or date range}
```

---

## Step 9 — Archive inbox files

Move processed text/markdown files to the processed inbox folder.
**For Immutable Assets (PDFs, PPTXs, Images):** Move these to the dedicated `Assets/` folder. They are Ground Truth and must never be modified. Use relative paths or Obsidian attachment syntax to reference them in your markdown.
