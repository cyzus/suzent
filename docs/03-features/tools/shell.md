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
| **Run command** | Runs a command and waits for it to finish |
| **Start command** | Starts a long-running command in the background |
| **Check command** | Reads new output from a background command and whether it has finished |
| **Stop command** | Stops a background command |

## Where commands run

| | Host mode (default) | Sandbox mode |
|---|---|---|
| **Runs on** | Your computer, using bash (macOS, Linux) or PowerShell (Windows) | An isolated Docker container |
| **Starts in** | The project workspace, or the folder chosen with **Working Dir** | `/workspace` |

To switch, see [Using the sandbox](../filesystem.md#using-the-sandbox). In host
mode, commands can reach the project folders through variables such as
`$PROJECT_PATH`; see [Where files go](../filesystem.md#where-files-go).

## Timeouts and output

A command run with **Run command** is stopped after 120 seconds, together with
anything it started, and the agent gets whatever output it produced so far. The
agent can give a single command a longer limit, or start it in the background
instead. To change the default, set `SUZENT_SHELL_TIMEOUT_MS` (in milliseconds)
in your `.env` file.

Very long output is cut to its last 30,000 characters, so the agent still sees
the end of a test run or build log. It is told where the full output was saved.

## Background commands

Long-running commands, such as a build or a dev server, can run in the
background while you keep chatting. The 120-second limit doesn't apply to them.

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
