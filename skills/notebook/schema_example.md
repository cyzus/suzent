# Notebook Schema

This file defines the architecture, conventions, and rules for this vault.
The AI reads it before every ingest, lint, or query operation. Edit it to match your vault.

Synthesized pages use the notebook skill's optional OKF-inspired profile. This improves
portability but does not declare full OKF conformance.

---

## Vault Structure

The vault is organized into layers by purpose:

- `0_Inbox/` — unclassified raw materials waiting to be processed (PDFs, clippings, screenshots). The AI processes files here and moves them to appropriate destinations.
- `1_Projects/` — active execution: TODO lists, roadmaps, meeting notes, project-specific docs. Do not store general knowledge or literature summaries here.
- `2_Wiki/` — the LLM-maintained, cross-linked knowledge layer:
  - `Concepts/` — evergreen, abstract ideas and theories
  - `Literature/` — summaries of specific papers, articles, or sources (1 source = 1 page)
  - `Syntheses/` — comparative analyses, cross-cutting insights, overviews
  - `Entities/` — specific concrete nouns (models, datasets, tools, people)
- `3_Personal/` — long-term personal tracking
- `4_Assets/` — read-only binary files (PDFs, images). Never modify.
- `5_Archives/` — completed or inactive work

---

## Where to Place New Synthesized Pages

| Content type | Destination |
|---|---|
| Abstract concept or theory | `2_Wiki/Concepts/` |
| Paper or article summary | `2_Wiki/Literature/` |
| Comparative or cross-cutting analysis | `2_Wiki/Syntheses/` |
| Specific model, dataset, or tool | `2_Wiki/Entities/` |

**Do not create a page for a topic that already has a folder or file.**
Link to what exists instead.

---

## Page Types

Every page in `2_Wiki/` must have YAML frontmatter. `type` is required; retain the other
fields when they carry useful information:

```yaml
---
type: concept | literature | synthesis | entity
title: Human-readable title
description: One-sentence summary
tags: []
status: draft | stable | deprecated
review: current | needs-review
confidence: high | medium | speculative
updated: YYYY-MM-DD
# Optional for time-sensitive knowledge
stale_after: YYYY-MM-DD
# Optional when the page derives from identifiable material
sources:
  - id: stable-source-id
    resource: URL or vault-relative path
    title: Source title
---
```

Use standard Markdown links with full vault-relative paths, for example
`[Temporal Reasoning](/2_Wiki/Concepts/Temporal%20Reasoning.md)`. For a claim tied to a
`sources` entry, use a matching footnote such as `[^stable-source-id]`.

Standard sections: `## Overview`, `## Key Facts`, `## Related`, `## Sources`.

### Personal pages (`3_Personal/`)

These hold consolidated facts about the user, so their lifecycle matters more than their
structure. Frontmatter:

```yaml
---
type: personal
title: Human-readable title
updated: YYYY-MM-DD
stale_after: YYYY-MM-DD
---
```

`stale_after` is required here. Derive it from the fact category rather than guessing:

| category | default lifetime |
|---|---|
| identity | none — omit `stale_after` |
| `preference` | 1 year |
| `technical` | 6 months |
| `goal` | 3 months |
| `context` | 3 weeks |

A claim the same user keeps repeating is one claim confirmed many times, not many claims.
Record that on the bullet rather than by restating it:

```markdown
- Wants to be reminded to drink water hourly from 9 AM to 9 PM. (confirmed 12x, last 2026-08-20)
```

Rules for the marker:

- Omit it entirely the first time a claim is written. A claim with no marker is confirmed once.
- On a repeat, increment the count and set the date. Never add a second bullet.
- When the repeat is *more specific*, replace the bullet text with the sharper wording and
  keep the accumulated count — the claim did not change, the phrasing got better.
- When the repeat *contradicts* the bullet, it is a correction or a change over time, not a
  confirmation. Reset the count and follow the correction rules above.

`## Overview` must be a coherent synthesis paragraph — not a stub or a list.
`## Related` links must use full vault-relative paths and explain the connection in one line.

---

## Naming Conventions

| Folder | Pattern | Example |
|---|---|---|
| `0_Inbox/` | Free-form — AI renames on ingest | — |
| `2_Wiki/Literature/` | `[YYYY] Short Title.md` | `[2026] Reasoning the World.md` |
| `2_Wiki/Entities/` | `[{Type}] Name.md` | `[Model] GPT-4o.md`, `[Dataset] TimeQA.md` |
| `2_Wiki/Concepts/` | Title Case, singular noun, no prefix | `Temporal Reasoning.md` |
| `2_Wiki/Syntheses/` | `[{Action}] Topic.md` | `[Compare] Causal Chain Approaches.md` |

---

## Index Categories

Section headings used in `index.md`:

- Concepts
- Literature
- Syntheses
- Entities

---

## Maintenance Rules

1. **Contradictions** — if Source A conflicts with Source B, add `> [!warning] Conflicting claims: [description]` on the page, set `review: needs-review`, and flag it in `log.md`.
2. **Stale pages** — honor `stale_after` first. Otherwise, a synthesis not updated in 90 days must be flagged `review: needs-review`. On personal pages, a passed `stale_after` means re-confirm the claim from recent logs or mark it `status: deprecated` — not delete it.
3. **No orphans** — every wiki page must link back to a concept page or appear in `index.md`.

---

## Domain-Specific Ingest Rules

### Academic Literature
When ingesting a paper or source:
1. Extract **Key Claims** — the core falsifiable argument.
2. Extract **Methodology / Innovations** — what is technically novel.
3. Note **Limitations** — when does the method fail or not apply.
4. **Cross-link** — link to the relevant concept page and related entities.
