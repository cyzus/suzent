---
sidebar_position: 2
title: Permissions & approvals
description: How Suzent asks before it acts, the three permission modes, and how to remember your answers.
---

# Permissions & approvals

**Sovereign authority.** This is where your agent's reasoning becomes action in
the world. A sovereign agent doesn't cross that line on its own terms: it stops
and asks, under rules you set. See
[what makes an agent sovereign](https://suzent.com/sovereign).

Reading is free. Anything that changes something, such as running a command,
writing or editing a file, sending a message, generating an image, or
clicking and typing in a desktop app, goes through a permission check first.

## Permission modes

Pick a mode per conversation from the mode selector next to the message box.

| Mode | What happens |
|---|---|
| **Ask** | Read-only actions run. Anything that changes files or the outside world asks you first. |
| **Smart** (default) | Clearly low-risk actions run on their own. Anything else is reviewed by a separate security model, which approves it, blocks it, or asks you. |
| **Full Access** | Actions run without asking. |

In every mode, your explicit "deny" rules and Suzent's built-in safety checks
(for example, blocked paths and dangerous shell commands) still apply. In Smart
mode, a shell command the safety checks would block is put to you instead of
refused outright, and if the reviewer can't decide, it asks you. The reviewer uses the **Permission
Review** model role, which falls back to **Decision**; see
[Model roles](../../04-models/model-roles.md). If that model can't be reached,
the chat's own model reviews the action instead, and only if that fails too
does Suzent ask you. The reviewer explains its
concern in the language you are writing in, and if you refuse a flagged action,
the agent is told why so it doesn't simply try the same thing again.

## Answering a request

When the agent needs approval, it pauses and asks above the message box,
"May I …?", usually with the reason it is asking. You can:

| Answer | What it does |
|---|---|
| **Allow** | Allow it this once. **Ctrl+Enter** does the same. |
| **Allow** menu (the arrow next to it) | Pick how long to remember: **Just once**, **Always allow for session** (the rest of this chat), or **Always allow globally** (every chat from now on). The button then shows your choice; click it to answer. |
| **Decline** | Refuse. To tell the agent why, or what to do instead, type in the box first and click **Decline & send**. |

For shell commands, the remember options name the command, for example
**This command · this chat** and **This command · always**, or
**Allow all git log … for session** and **Always allow all git log …**.
That remembers that command, or that command prefix, not every command. Inline
scripts can only be allowed once. A pending request survives a page refresh, so
you can come back to it later.

## Where rules are kept

Session rules live with the chat. "Always allow" rules are saved in
`permissions.yaml` in your Suzent config folder (`~/.suzent/config/`), where you
can review or remove them. Every decision is also logged to
`permission-audit.jsonl` in the same folder, with secrets redacted.

## When nobody is watching

Scheduled tasks, heartbeats, goals, sub-agents, and memory consolidation run in
the background, where nobody can answer. They always use Smart mode,
whatever mode the chat that created them uses, and anything the reviewer can't
clear as safe is denied instead of waiting for an answer. See
[Automation](../automation.md).

The one exception is heartbeats: under **Settings → Automation → Heartbeat Tool
Approvals** you can pick tools that a heartbeat may run without review.
