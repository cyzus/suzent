# Notebook Schema

This file defines the architecture, conventions, and rules for this vault.
The AI reads it before every ingest, lint, or query operation. Edit it to match your vault.

---

## Vault Structure

The vault is organized into layers by purpose:

- `0_Inbox/` — unclassified raw materials waiting to be processed (PDFs, clippings, screenshots). The AI processes files here and moves them to appropriate destinations.
- `1_Projects/` — active execution: TODO lists, roadmaps, meeting notes, project-specific docs. Do not store general knowledge or literature summaries here.
- `2_Wiki/` — the LLM-maintained knowledge layer, highly interconnected via `[[wikilinks]]`:
  - `Concepts/` — evergreen, abstract ideas and theories
  - `Literature/` — summaries of specific papers, articles, or sources (1 source = 1 page)
  - `Syntheses/` — comparative analyses, cross-cutting insights, overviews
  - `Entities/` — specific concrete nouns (models, datasets, tools, people)
- `3_Personal/` — long-term personal tracking
- `4_Assets/` — read-only binary files (PDFs, images). Never modify. Reference via wikilinks.
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

Every page in `2_Wiki/` must have YAML frontmatter:

```yaml
---
type: concept | literature | synthesis | entity
status: active | superseded | needs-review
confidence: high | medium | speculative
updated: YYYY-MM-DD
---
```

Standard sections: `## Overview`, `## Key Facts`, `## Related`, `## Sources`.

`## Overview` must be a coherent synthesis paragraph — not a stub or a list.
`## Related` links must use full vault paths and explain the connection in one line.

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

1. **Contradictions** — if Source A conflicts with Source B, add `> [!warning] Conflicting claims: [description]` on the page and flag it in `log.md`.
2. **Stale pages** — any `type: synthesis` page with `status: active` not updated in 90 days must be flagged `status: needs-review`.
3. **No orphans** — every wiki page must link back to a concept page or appear in `index.md`.

---

## Domain-Specific Ingest Rules

### Academic Literature
When ingesting a paper or source:
1. Extract **Key Claims** — the core falsifiable argument.
2. Extract **Methodology / Innovations** — what is technically novel.
3. Note **Limitations** — when does the method fail or not apply.
4. **Cross-link** — always link to the relevant concept page and related entities.
