---
sidebar_position: 4
title: Share memory with other agents
description: Let Claude Code, Codex, Cursor and other AI apps on your computer search your Suzent memory, and save to it if you allow it.
---

# Share memory with other agents

Suzent remembers who you are, what you prefer, and what worked last time. Other AI
apps you use can share that memory, so you don't have to explain yourself again in
Claude Code, Codex or Cursor.

Your memory stays sovereign: it never leaves your computer. The other app talks to
the Suzent running on the same machine, and Suzent stays the only one that keeps
the files.

## Connect an app

Suzent needs to be running. Then add it to the app as an MCP server.

**Claude Code**

```bash
claude mcp add suzent -- suzent mcp serve
```

**Codex**

```bash
codex mcp add suzent -- suzent mcp serve
```

**Other apps** (Cursor, Claude Desktop, Windsurf and others): add an MCP server
that runs on your computer, with the command `suzent` and the arguments
`mcp serve`. In a JSON settings file that looks like this:

```json
{
  "mcpServers": {
    "suzent": { "command": "suzent", "args": ["mcp", "serve"] }
  }
}
```

The same command is in **Settings → Memory System → Other agents**, with a button
to copy it.

## What the app can do

| Tool | What it does |
|---|---|
| `memory_search` | Search your memory by meaning, for example "which package manager do I like". |
| `memory_profile` | Read what Suzent knows about you: who you are, your preferences, and key facts. |
| `memory_remember` | Save something new. Off until you allow it. |

Reading is always allowed for apps on your computer. Saving is off until you turn
on **Let them save memories** in **Settings → Memory System → Other agents**.

When an app saves a memory:

- It is marked with the app that wrote it, such as `claude-code`, so you can always
  tell it apart from what you said to Suzent yourself.
- Suzent files it into your notes the same way as everything else. What you tell
  Suzent directly still wins if the two disagree.
- The app can only add. It can't change or delete anything that is already there.
  To correct a memory, tell Suzent.

## Teach the app when to use it

The tools work on their own, but a skill tells the app when to look things up and
when to save. Install it for Claude Code with:

```bash
suzent mcp skill --dir ~/.claude/skills
```

For Codex, use `--dir ~/.codex/skills`. Run `suzent mcp skill` without `--dir` to
print the skill and paste it wherever your app keeps its instructions.

## Troubleshooting

**"Cannot connect to Suzent server"**: start Suzent first, with the app or
`suzent start`.

**"Writing memories from other agents is off"**: turn on **Let them save memories**
in **Settings → Memory System → Other agents**.

**The app says `suzent` is not found**: the app can't see the `suzent` command.
Use its full path instead. Run `which suzent` (macOS and Linux) or `where suzent`
(Windows) in a terminal to find it.

Apps on another computer can't connect yet. The server only talks to the Suzent on
the same machine.
