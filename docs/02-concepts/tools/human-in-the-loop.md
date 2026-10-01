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
writing or editing a file, sending a message, or generating an image, goes
through a permission check first.

## Permission modes

Pick a mode per conversation from the mode selector next to the message box.

| Mode | What happens |
|---|---|
| **Ask** (default) | Read-only actions run. Anything that changes files or the outside world asks you first. |
| **Smart** | Clearly low-risk actions run on their own. Anything else is reviewed by a separate security model, which approves it, blocks it, or asks you. |
| **Full Access** | Actions run without asking. |

In every mode, your explicit "deny" rules and Suzent's built-in safety checks
(for example, blocked paths and dangerous shell commands) still apply. In Smart
mode, if the reviewer can't decide, it asks you. The reviewer uses the **Permission
Review** model role, which falls back to **Decision**; see
[Model roles](../providers/model-roles.md).

## Answering a request

When the agent needs approval, it pauses and shows what it wants to do. You can:

- **Allow** it once.
- **Allow for session**, so the same action is allowed for the rest of this
  chat.
- **Always allow**, so it is allowed in every chat from now on.
- **Deny** it, optionally telling the agent what to do instead.

For shell commands, "allow" remembers that exact command, or a command prefix
such as `git log`, not every command. A pending request survives a page
refresh, so you can come back to it later.

## Where rules are kept

Session rules live with the chat. "Always allow" rules are saved in
`permissions.yaml` in your Suzent config folder (`~/.suzent/config/`), where you
can review or remove them. Every decision is also logged to
`permission-audit.jsonl` in the same folder, with secrets redacted.

## When nobody is watching

Scheduled tasks, heartbeats, goals, sub-agents, and memory consolidation run in
the background, where nobody can click "Allow". They always use Smart mode,
whatever mode the chat that created them uses, and anything the reviewer can't
clear as safe is denied instead of waiting for an answer. See
[Automation](../automation.md).

The one exception is heartbeats: under **Settings → Automation → Heartbeat Tool
Approvals** you can pick tools that a heartbeat may run without review.
