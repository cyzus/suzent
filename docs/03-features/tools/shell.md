---
sidebar_position: 4
title: Commands
description: How your agent runs commands, where they run, background commands, and which commands need your approval.
---

# Commands

The **Shell** tools let the agent run commands: install a package, run your
tests, start a build or a dev server.

| Tool | What it does |
|---|---|
| **Run command** | Returns the result of a quick command, or an ID if it is still running after 10 seconds |
| **Start command** | Starts a long-running command in the background |
| **Check command** | Reads new output from a background command and whether it has finished |
| **Stop command** | Stops a background command |

## Where commands run

| | Host mode (default) | Sandbox mode |
|---|---|---|
| **Runs on** | Your computer, using bash (macOS, Linux) or PowerShell (Windows) | An isolated Docker container |
| **Starts in** | The project's `scratch/` folder, or the folder chosen with **Working Dir** | `/workspace/scratch` |

To switch, see [Using the sandbox](../filesystem.md#using-the-sandbox). In host
mode, commands can reach the project folders through variables such as
`$PROJECT_PATH`; see [Where files go](../filesystem.md#where-files-go).

## Timeouts and output

**Run command** shows output as the command produces it. If the command is still
running after 10 seconds, the agent receives its output so far and a command ID.
It can continue working, read later output with **Check command**, or end the
process with **Stop command**. The command's completion also notifies the agent.
For a command that must finish within a set time, the agent can specify a timeout;
Suzent then stops the command and anything it started when that limit is reached.

Very long output is cut to its last 30,000 characters, so the agent still sees
the end of a test run or build log. It is told where the full output was saved.

## Background commands

Long-running commands, such as a build or a dev server, can run in the
background while you keep chatting. A command that **Run command** returns with
an ID also appears here.

Open the **Background tasks** panel in the right sidebar to see them, alongside
any sub-agents. Click a **Shell command** to see its status, exit code, and
**Output (latest)**, which updates as the command runs. To end it, click the
stop button.

When a background command finishes, the agent is told its exit code and the end
of its output, and picks up where it left off, even if you have moved on. If you
stop a command yourself, the agent isn't woken up for it.

While a command runs, the agent can use **Check command** to read new output,
or **Stop command** to end it.

## Approval

How commands are approved depends on the
[permission mode](./human-in-the-loop.md#permission-modes) and on the command
itself. **Run command** and **Start command** follow these rules:

| Command | **Ask** | **Smart** | **Full Access** |
|---|---|---|---|
| Read-only, such as `ls`, `cat`, `grep`, `wc` | Runs | Runs | Runs |
| `mkdir`, `touch`, `cp` | Asks | Runs | Runs |
| Any `git` command, or commands joined with `&&`, `\|`, or `;` | Asks | Reviewer | Runs |
| Everything else, including `rm` and `mv` | Asks | Reviewer | Runs |
| Dangerous, such as `sudo`, `chmod`, `dd`, `shutdown` | Blocked | Asks you | Blocked |

"Reviewer" means Smart mode's security model decides, and may ask you. In
background runs, where nobody can answer, anything that would ask you is denied.

Deleting a whole drive or system folder, such as `rm -rf /` or `/etc`, is
treated as dangerous too. When a common file command such as `cat` or `cp`
points outside the folders the agent can reach, it asks first in host mode and
is refused in the sandbox.

**Check command** never asks. **Stop command** asks in **Ask** mode, goes to the
reviewer in **Smart** mode, and runs in **Full Access**.

When you approve a command, you can remember the answer for this chat or for
every chat. Suzent remembers a prefix where it can: approving
`git log --oneline` offers **Yes, allow all git log … for this session**, which
also covers `git log -5` but not `git push`. Commands joined with `&&` or `|` are
remembered exactly as written.

## Undo

Changes made by commands, such as installed packages or files a script wrote,
are not rolled back by [Retry](../filesystem.md#undoing-the-last-turn-retry).
Use [Files](./files.md) tools for edits you may want to undo, and keep Git or
backups for anything important.
