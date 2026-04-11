---
name: notebook
description: Access and maintain the notebook knowledge base with Obsidian markdown conventions.
---

# Notebook Skill

The notebook is your personal vault and knowledge base. You read and write it using
standard file tools (`ReadFileTool`, `WriteFileTool`, `EditFileTool`, `GlobTool`,
`GrepTool`).

Path rules by execution mode:
- Sandbox Mode: notebook root is `/mnt/notebook`.
- Host Mode: notebook root is `${MOUNT_NOTEBOOK}` if mounted.

**Always read `schema.md` from the notebook root before doing any work in the notebook.**
The schema defines this vault's structure, conventions, and rules. Follow it exactly.

Operational procedures:
- Ingest: `notebook/ingest.md` under your skills root.
- Lint: `notebook/lint.md` under your skills root.

---

## Navigation Files

Three files at the notebook root are agent-maintained:

**`schema.md`** — vault conventions, folder layout, page types, index categories.
The authoritative source for how to work with this notebook. Read it first, every time.

**`index.md`** — catalog of synthesized pages. Revised freely on every ingest or query filing.
Format: `- [[path/to/page]] — one-line summary`, organized by category per schema.md.

**`log.md`** — append-only chronological record. Never edit existing entries.
Required prefix per entry: `## [YYYY-MM-DD] operation | description`
Operations: `ingest`, `query-filed`, `lint`

---

## Obsidian Markdown

- CommonMark + GitHub Flavored Markdown
- LaTeX for math
- Wikilinks: `[[page]]` or `[[path/to/page]]` — use full vault paths
- Callouts: `> [!note]`, `> [!warning]`

---

## Page Format

```yaml
---
type: <per schema.md>
name: Canonical Name
aliases: []
tags: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

Standard sections: `## Overview`, `## Key Facts`, `## Related`, `## Sources`.
Use whatever additional sections the content warrants.

`## Overview` must be a coherent synthesis paragraph — not a stub, not a list.
`## Related` links must use full vault paths and explain the connection in one line.

---

## When to File a Query Result

When a conversation produces something durable — a comparison, analysis, synthesis,
or decision — file it back into the notebook rather than letting it disappear.

1. Write the page in the location specified by schema.md
2. Add an entry to `index.md`
3. Append a `query-filed` entry to `log.md`
