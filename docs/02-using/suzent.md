---
sidebar_position: 3
title: SUZENT, the agent at the top of the sidebar
description: Talk to SUZENT to see every project at once, hand work to project sessions, and hear only about what needs you.
---

# SUZENT, the agent at the top of the sidebar

**SUZENT** sits above your chats in the sidebar. It is the one conversation
that watches all of your projects: you tell it what you want done, it hands
the work to a session in the right project, follows up while you are away,
and tells you when something needs your decision.

Use it when you don't want to open each project to see where things stand,
or when you want to say "get this done" and come back later.

## How it differs from your other chats

| | SUZENT | A chat in a project | A chat in Home |
|---|---|---|---|
| How many | Exactly one, always there | As many as you like per project | As many as you like |
| What it can see | Every project, its sessions and tasks | Its own project | Its own conversation |
| Does the work itself | No: it hands work to project sessions and follows up | Yes: edits files, runs commands, uses your tools | Yes, with the tools you pick |
| Reaches out to you | Yes: check-ins, reminders, and anything waiting on you | Only in its own chat | Only in its own chat |
| Tools | A fixed set, shown in its **Tools** tab | The ones you pick | The ones you pick |

The short version: chats in a project do the work; SUZENT keeps track of all
of it for you.

## Hand it work

Tell SUZENT what you want, and which project it belongs to if that isn't
obvious. It either:

- **sends the work to a session already in that project**, waking it up with
  your request, or
- **starts a new session in the project** to take it on, with a task on the
  project's task list.

Your request shows up at the start of the new session, so you can open it any
time and see what was asked. The session then works on its own. When it
finishes, or gets stuck on something only you can answer, it reports back to
SUZENT, and SUZENT tells you.

:::caution
Sessions that SUZENT starts run in **Smart** mode: low-risk actions go ahead,
and anything else is reviewed by the security model, which may still ask you.
Your deny rules and the built-in safety checks apply as usual. To have a
session ask before every change, open it and switch its mode to **Ask**. See
[Permission modes](../03-features/tools/human-in-the-loop.md#permission-modes).
:::

## See what's going on

The SUZENT card in the sidebar shows, at a glance:

- **waiting on you**: tasks blocked on your answer or on an error,
- **stalled**: sessions with work left that have stopped moving,
- **auto-running**: sessions working right now.

Projects and chats holding something that waits on you get a badge in the
sidebar too. Inside SUZENT, the **Tasks** side panel shows the board for every
project at once, grouped by session; pick one project to narrow it down.

## It checks in on its own

SUZENT has a [heartbeat](../03-features/automation.md#heartbeat) that is on from
the start and runs every 30 minutes. A check-in looks for sessions that have
stalled and for questions you haven't answered in a while. When everything is
fine, it stays quiet and nothing is added to the chat.

To change what it looks for, edit its `heartbeat.md` checklist from SUZENT's
**Config** tab. You can also change how often it runs, or turn it off; turning
it off sticks.

## Reminders and follow-ups

Ask SUZENT to remind you of something, or to check back on some work later:

> Remind me at 5pm to send the weekly update.
>
> Check on the docs rewrite in an hour and tell me if it's stuck.

A **reminder** always tells you. A **check** only tells you if there is
something worth saying. Both are listed under **Scheduled wake-ups** in
SUZENT's **Tools** tab, where you can cancel them.

When SUZENT says something while you are elsewhere, its card shows the new
message and you get a desktop notification.

## What it remembers about working with you

SUZENT keeps its own short notes on how you want it to work: what to bring to
you and what to handle itself, what counts as urgent, when not to disturb you,
which project you mean by a nickname, and how you like your reports. Tell it a
rule ("don't ping me about tests failing, just restart them") and it writes it
down; it also notes rules you keep repeating.

It reads these notes at the start of every turn. They never hold project or
task status, which it looks up fresh each time. To read or change them
yourself, open SUZENT's **Context** tab and click **Edit**.

What it learns about *you* in general goes to your
[memory](../03-features/memory/README.md), like any other chat.

## What it won't do

SUZENT can read files and search the web, your memory, and past
conversations, but apart from its own notes it can't edit files, run commands, or use MCP servers, and
the tool picker doesn't apply to it. That keeps one agent with a view of every
project from making changes in all of them at once: the work happens in a
project session, where you can see and steer it.

SUZENT only knows about a project's sessions through their tasks and what's
running. A chat in a project that never made a task and isn't running doesn't
show up for it.
