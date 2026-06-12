---
name: skill-creator
description: Create a new Suzent AgentSkill, or improve an existing one. Use when the user wants to author a skill from scratch, scaffold a SKILL.md with supporting scripts/references/assets, or refine a skill's description so it triggers reliably.
---

## Overview

This skill helps you author a new Suzent AgentSkill end to end: capture intent,
scaffold the directory, write a focused `SKILL.md`, and reload it so it becomes
available immediately.

A Suzent skill is a directory containing a `SKILL.md` (required) plus optional
`scripts/`, `references/`, and `assets/`. User-authored skills live under the
**`user` bucket** at `~/.suzent/skills/user/<name>/`.

> **Frontmatter constraint (important).** Suzent parses frontmatter with a
> simple line-by-line `key: value` reader — it only understands flat
> `name:` and `description:` fields and does **not** parse nested YAML
> (no `metadata:` blocks, no lists). Keep frontmatter to exactly these two keys.

## Workflow

### 1. Capture intent

Before writing anything, clarify with the user:
- **What** the skill does (the capability or SOP it encodes).
- **When** it should trigger — the concrete situations and phrasings. This drives
  the `description`, which is what the agent matches against.
- **What output** is expected, and whether the skill needs bundled `scripts/`
  (executable helpers) or `references/` (docs the agent reads on demand).

### 2. Scaffold the directory

Run the bundled helper to create the skeleton in the user bucket:

```bash
python scripts/scaffold.py "<skill-name>" --description "<one-line trigger description>"
```

This creates `~/.suzent/skills/user/<skill-name>/` with a starter `SKILL.md` and
empty `scripts/`, `references/`, `assets/` directories. It refuses to overwrite
an existing skill unless `--force` is passed.

In **sandbox mode** the `~/.suzent` path may not be writable directly — write the
skill via the filesystem skill / `SUZENT_BASE_URL` instead, mirroring the same
layout.

### 3. Author SKILL.md

Edit the scaffolded `SKILL.md`. Guidelines that make skills work well:
- Keep the body focused — under ~500 lines. Link to `references/` for depth.
- Write the **description** as trigger language: name the situations and verbs a
  user would actually use. A vague description is the most common reason a skill
  never fires.
- Prefer explaining *why* an instruction matters over rigid "ALWAYS/NEVER" rules,
  so the agent can generalize.
- If you add executable helpers, put them in `scripts/` and document how to call
  them from the body.

### 4. Reload and verify

Make the skill available without restarting:

```bash
suzent skill reload
suzent skill list          # confirm it appears under the 'user' source
suzent skill toggle <name> # enable it if it is off
```

Then test with 2–3 realistic prompts that *should* trigger it, and a couple that
should *not*, to check the description isn't over- or under-matching. Refine the
description and repeat.

## Notes / scope

- This v1 covers scaffolding + authoring + reload. Eval harnesses and `.skill`
  packaging are intentionally out of scope for now.
- To distribute a skill to others, share the directory; the recipient installs it
  via the `skill-installer` skill.
