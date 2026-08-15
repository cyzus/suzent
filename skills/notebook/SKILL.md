---
name: notebook
description: Read, organize, ingest, lint, or file durable knowledge in a configured Obsidian-compatible notebook. Use only for explicit notebook/vault work or when an enabled capture policy asks for a result to be filed.
---

# Notebook

Resolve the notebook root from the execution context:

- Sandbox: `/mnt/notebook`
- Host: `${MOUNT_NOTEBOOK}` when configured

Before changing the notebook, read `schema.md` completely. Accept `SCHEMA.md` only when
that is the actual filename. The vault schema is the sole authority for directories,
frontmatter, naming, indexes, staleness rules, and cross-link conventions. Do not copy
defaults from this skill over a vault-specific rule.

If no notebook is configured, report that and skip notebook changes.

## Core files

- `schema.md`: user-owned conventions; never rewrite unless explicitly requested.
- `index.md`: agent-maintained catalog; update according to the schema.
- `log.md`: append-only operation history; never prepend, reorder, or edit an existing
  entry unless the schema explicitly defines a different log policy.

Use Obsidian wikilinks and callouts only where the existing vault uses them. Prefer full
vault-relative paths when links could be ambiguous.

## Procedures

- For source consolidation, read `ingest.md` in this skill directory.
- For structural and contradiction checks, read `lint.md` in this skill directory.

Read the selected procedure completely before acting. Treat referenced binary assets as
immutable unless the user explicitly asks to replace them.

## Filing conversation results

File a result only when the user explicitly requests it or the vault/session has an
enabled capture policy. Do not turn ordinary conversations into unsolicited notebook
writes.

When filing is authorized:

1. Follow `schema.md` for the destination and page structure.
2. Update `index.md` only when required by the schema.
3. Append a `query-filed` entry to `log.md` when the log convention requires it.
