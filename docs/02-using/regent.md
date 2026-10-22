---
sidebar_position: 3
title: Suzent Regent, the agent at the top of the sidebar
description: Talk to Regent to see every project at once, hand work to project sessions, and hear only about what needs you.
---

# Suzent Regent, the agent at the top of the sidebar

**Suzent Regent**, or Regent for short, sits above your chats in the sidebar. It is the one conversation
that watches all of your projects: you tell it what you want done, it hands
the work to a session in the right project, follows up while you are away,
and tells you when something needs your decision.

Use it when you don't want to open each project to see where things stand,
or when you want to say "get this done" and come back later.

## How it differs from your other chats

| | Regent | A chat in a project | A chat in Home |
|---|---|---|---|
| How many | Exactly one, always there | As many as you like per project | As many as you like |
| What it can see | Every project, its sessions and tasks | Its own project | Its own conversation |
| Does the work itself | No: it hands work to project sessions and follows up | Yes: edits files, runs commands, uses your tools | Yes, with the tools you pick |
| Reaches out to you | Yes: check-ins, reminders, and anything waiting on you | Only in its own chat | Only in its own chat |
| Tools | A fixed set, shown in its **Tools** tab | The ones you pick | The ones you pick |

The short version: chats in a project do the work; Regent keeps track of all
of it for you.

## Hand it work

Tell Regent what you want, and which project it belongs to if that isn't
obvious. It either:

- **sends the work to a session already in that project**, waking it up with
  your request, or
- **starts a new session in the project** to take it on, with a task on the
  project's task list.

It can also hand the work to a coding agent you've set up under
**Settings → ACP Agents**, such as Codex or Claude Code: say "have Codex fix
this in the website project" and Regent starts a session in that project that
runs on Codex.

It can also message Suzent on your other paired devices, for example to run
something on your laptop. It sends the message and moves on; the reply comes
back to it later.

Your request shows up at the start of the new session, so you can open it any
time and see what was asked. The session then works on its own. When it
finishes, or gets stuck on something only you can answer, it reports back to
Regent, and Regent tells you.

:::caution
Sessions that Regent starts run in **Smart** mode: low-risk actions go ahead,
and anything else is reviewed by the security model, which may still ask you.
Your deny rules and the built-in safety checks apply as usual. To have a
session ask before every change, open it and switch its mode to **Ask**. See
[Permission modes](../03-features/tools/human-in-the-loop.md#permission-modes).

Sessions on a coding agent start in **Ask** mode instead, since there is no
security model to review their actions. Open the session to approve what it
asks; a request nobody answers is denied after a while, and the agent reports
that back.
:::

## See what's going on

The Regent card in the sidebar shows, at a glance:

- **waiting on you**: tasks blocked on your answer or on an error,
- **stalled**: sessions with work left that have stopped moving,
- **auto-running**: sessions working right now.

Projects and chats holding something that waits on you get a badge in the
sidebar too.

Regent sits at the very top of the sidebar, above everything else, like a
pinned contact. Inside its chat, the header grows a second line under Regent's
name and picture: what it's doing, what **needs you** and what has **stalled**,
and how many wake-ups it has set. Click a session there to open it, or
**Board** to see every task in the side panel. The **Tasks** side panel shows the full board for every project at
once, grouped by session; pick one project to narrow it down.

Regent's picture tells you its state at a glance, here and on the sidebar card:

- **Still:** nothing needs you.
- **Eyes scanning:** it's checking in on sessions or answering you.
- **Orange gem:** something is waiting on your decision.
- **A small nod:** it just said something new.

If your system is set to reduce motion, the picture stays still.

## It checks in on its own

Regent has a [heartbeat](../03-features/automation.md#heartbeat) that is on from
the start and runs every 30 minutes. A check-in looks for sessions that have
stalled and for questions you haven't answered in a while. When everything is
fine, it stays quiet and nothing is added to the chat.

To change what it looks for, edit its `heartbeat.md` checklist from Regent's
**Config** tab. You can also change how often it runs, or turn it off; turning
it off sticks.

## Reminders and follow-ups

Ask Regent to remind you of something, or to check back on some work later:

> Remind me at 5pm to send the weekly update.
>
> Check on the docs rewrite in an hour and tell me if it's stuck.

A **reminder** always tells you. A **check** only tells you if there is
something worth saying. Both are listed under **Scheduled wake-ups** in
Regent's **Tools** tab, where you can cancel them.

When Regent says something while you are elsewhere, its card shows the new
message and you get a desktop notification.

## What it remembers about working with you

Regent keeps its own short notes on how you want it to work: what to bring to
you and what to handle itself, what counts as urgent, when not to disturb you,
which project you mean by a nickname, and how you like your reports. Tell it a
rule ("don't ping me about tests failing, just restart them") and it writes it
down; it also notes rules you keep repeating.

The notes start with empty sections, **Bring to the user**, **Handle without
asking**, **Don't disturb**, **Project names**, and **Reports**, and each rule
goes under the one it belongs to. Regent reads them at the start of every turn.
They never hold project or task status, which it looks up fresh each time; for
what a project is about, it reads a line from that project's own context
instead of keeping a copy. To read or change them
yourself, open Regent's **Context** tab and click **Edit**.

What it learns about *you* in general goes to your
[memory](../03-features/memory/README.md), like any other chat.

## What it won't do

Regent can read files and search the web, your memory, and past
conversations, but apart from its own notes it can't edit files, run commands, or use MCP servers, and
the tool picker doesn't apply to it. That keeps one agent with a view of every
project from making changes in all of them at once: the work happens in a
project session, where you can see and steer it.

Regent only knows about a project's sessions through their tasks and what's
running. A chat in a project that never made a task and isn't running doesn't
show up for it.
