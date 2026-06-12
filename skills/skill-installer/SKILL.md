---
name: skill-installer
description: Install a Suzent AgentSkill from a Git repo, ZIP URL, or owner/repo GitHub shorthand. Use when the user wants to add a third-party or community skill to Suzent. Fetches and copies only; never executes fetched code at install time.
---

## Overview

This skill installs an AgentSkill into Suzent's **`user` bucket**
(`~/.suzent/skills/user/<name>/`) from one of:

- a **Git repo** URL (ends in `.git` or is a recognizable repo URL),
- a **ZIP** URL (ends in `.zip`), or
- a **GitHub shorthand** `owner/repo` or `owner/repo/path/to/skill`.

It fetches files only — it does **not** run any code from the fetched source at
install time (no `npm install`, no post-install scripts). Bundled `scripts/` in
the installed skill run later, at *use* time, through the agent's normal
sandboxed tool path. "owner/repo shorthand" is a source-naming convenience and
resolves to a GitHub fetch; it does not invoke `npx` or any package.

The agent runs this on the user's explicit request ("install the skill at X"),
in a conversation the user is watching, so there is no separate trust prompt:
install fetches the source the user named, confirms it is a real skill, and
copies it in. The actual safety boundary is at *use* time — any `scripts/` the
installed skill runs go through the agent's normal sandboxed tool approval.

## Workflow

### 1. Run the installer

```bash
python scripts/install.py "<source>" [--name <name>] [--activate]
```

- `<source>` — a Git URL, ZIP URL, or `owner/repo[/path]`.
- `--name` — override the inferred skill name (default: last path segment).
- `--activate` — enable the skill after install (otherwise it installs disabled).

The script:
1. Resolves the source type and target name.
2. Fetches into a temp dir (`git clone --depth 1`, or download + unzip), with a
   size cap so a runaway fetch can't half-install.
3. Locates the `SKILL.md` (resolving into a subdirectory for monorepos) and
   validates that its frontmatter parses under Suzent's loader (flat
   `name:`/`description:` only — see the `skill-creator` skill).
4. Copies the validated directory to `~/.suzent/skills/user/<name>/`, cleaning up
   on any failure.

### 2. Activate and verify

```bash
suzent skill reload
suzent skill list
suzent skill toggle <name>   # if not installed with --activate
```

In **sandbox mode**, prefer the filesystem skill / `SUZENT_BASE_URL` for any
direct file writes, and call `POST /skills/reload` to surface the new skill.

## Notes / scope

- v1 is strictly fetch-and-copy. No setup/post-install steps are run.
- If validation fails (missing `SKILL.md`, or frontmatter Suzent can't load), the
  install aborts and the partial download is removed — report the reason to the
  user.
