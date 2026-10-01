---
sidebar_position: 4
title: Skills
description: Teach your agent new know-how with portable SKILL.md packages, install community skills, or write your own.
---

# Skills

**Sovereign mind.** Skills are knowledge you author and own. They are Markdown
files in your own folders, not a feature a platform grants and can take away,
so they keep working when you change models or providers. See
[what makes an agent sovereign](https://suzent.com/sovereign).

A **tool** lets the agent *do* something, like run a command. A **skill**
teaches it *how* to do something well: a workflow, a house style, the steps for
a particular system. The agent sees a one-line description of each enabled
skill and reads the full instructions only when a task calls for them.

## Built-in skills

| Skill | What it teaches |
|---|---|
| `notebook` | Keep your [notebook](./memory/llm-wiki.md) organized according to its `schema.md`. |
| `suzent-automation` | Create and manage [scheduled tasks and heartbeats](./automation.md). |
| `suzent-canvas` | Show tables, forms, and dashboards in the app. |
| `suzent-devices` | Use your [paired devices](./nodes.md) and other Suzent agents. |
| `social` | Format replies well for Telegram, Slack, Discord, Feishu, and WeChat. |
| `suzent-skill-creator` | Write a new skill, or improve an existing one. |
| `suzent-skill-installer` | Install a skill from a Git repository, ZIP link, or GitHub `owner/repo`. |

## Managing skills

Open **Skills** in the app's navigation to browse every skill Suzent found,
read it, and switch it on or off. Click **Reload from disk** after adding or
editing skill files.

## Adding skills

**Ask the agent.** The quickest way is to say "install the skill at
github.com/owner/repo" or "create a skill for how I like release notes
written". The built-in installer and creator skills take it from there.

**Or add a folder yourself.** A skill is a folder containing a `SKILL.md`
file. Put it in `~/.suzent/skills/`:

```text
~/.suzent/skills/
└── release-notes/
    ├── SKILL.md          # Required
    ├── scripts/          # Optional helper scripts
    ├── references/       # Optional longer documents
    └── assets/           # Optional templates, images, data
```

`SKILL.md` starts with a short header, followed by plain Markdown instructions:

```markdown
---
name: release-notes
description: Write release notes in our house style. Use when drafting or editing release notes.
---

# Release notes

## Style

- Lead with what changed for users, not how.
- Group changes under Added, Changed, and Fixed.

## Checklist

- Link each item to its pull request.
```

The `description` decides when the agent reaches for the skill, so say both
what it does and when to use it. Keep the body short and practical, and move
long material into `references/`.

## Where Suzent finds skills

- **Bundled** skills that ship with Suzent.
- **User** skills in `~/.suzent/skills/`.
- **Repository** skills in the project you are working in: a `skills/` folder,
  or `.claude/skills/`, `.agents/skills/`, `.codex/skills/`, or `.grok/skills/`.
  Skills written for other agents that use the same `SKILL.md` format work as
  they are.
- **Custom** folders listed in the `SKILLS_DIR` environment variable.

Suzent also follows `AGENTS.md` and `CLAUDE.md` files in your working directory
and its parent folders, the same way other coding agents do. The chat sidebar's
**Context** tab shows which instructions are in effect.

## Troubleshooting

**A skill doesn't appear.** Check that the file is named exactly `SKILL.md`,
that the header has both `name` and `description` between `---` lines, then
click **Reload from disk**.

**The agent never uses a skill.** Make sure it is enabled, and make the
`description` more specific about when it applies.
