---
slug: what-is-regent
title: "What Is Regent? Suzent's Orchestration Layer"
description: "Why your AI setup shouldn't turn you into a full-time dispatcher: how Regent acts as a single point of attention across autonomous project sessions, and how it differs from sub-agents."
authors: [suzent]
tags: [regent, multi-agent, orchestration, architecture]
date: 2026-10-26T10:00:00
---

The first time an AI agent finishes a real task for you, you give it a second
one. Then a third. Within a week you have one session benchmarking a parser,
another drafting a release post, a third triaging literature, and a fourth
watching a deployment.

You are no longer doing the work. You are doing something just as exhausting:
**you have become the router.**

**Regent** is Suzent's answer to that ceiling. Instead of facing a sidebar full
of parallel sessions and polling each one yourself, you talk to a single
orchestrator that dispatches work across your projects and only comes back when a
decision belongs to you.

<!-- truncate -->

## Why "Regent"?

Historically, a *regent* governs a realm in the monarch's stead — handling the
day-to-day administration of state, coordinating ministers, and bringing only
matters of sovereign consequence to the crown.

In early builds of Suzent, this singleton chat was simply called **SUZENT** (and
in the codebase it still lives in `suzent.core.focal_agent`, with the fixed chat
ID `focal-suzent`). As multi-project workflows matured, the generic name hid
what made the role distinct: it is not "the main chatbot." You are the
sovereign; Regent is the executive layer that governs your autonomous sessions
while you focus elsewhere.

<img src="/img/regent-sovereign-delegation.svg" width="880" height="390" alt="The Sovereign and the Regent: you hold the crown and set direction, delegating day-to-day governance of project ministers to Regent, who returns only for royal assent." />

## What Regent actually is

Instead of forcing you to act as a human router across a dozen tabs, Regent sits
at the top of the desktop sidebar as a pinned card above your projects.

<img src="/img/regent-evolution.svg" width="880" height="420" alt="Before and after Regent: moving from human-as-router across many chat tabs to a single point of attention." />

Three strict rules define how it operates:

1. **A single point of attention.** You do not juggle tabs for *Research*,
   *Coding*, *Writing*, and *Ops*. You talk to Regent in one continuous
   conversation, and Regent routes work to the right project behind the scenes.

2. **A dispatcher, never a doer.** Regent does not write code, edit documents,
   or run shell commands. Those tools are stripped from its runtime policy. When
   you ask for project work, Regent uses `agent_dispatch` to wake or spawn a
   primary session inside that project — or hand the job to a configured coding
   agent over the [Agent Client Protocol (ACP)](https://suzent.com/docs/developing/protocols/acp).

3. **A filter, not a relay.** When a project session finishes or hits a blocker,
   it reports to Regent's inbox. Regent never dumps a 4,000-character execution
   log into your chat. It distills the outcome to a single sentence — or, if
   nothing needs your input, records the completion silently without notifying
   you at all.

<img src="/img/regent-architecture.svg" width="880" height="580" alt="Regent architecture blueprint showing the full hierarchy: You at the top, Regent orchestrating across projects, autonomous Project Primary Sessions, and task-scoped Sub-agents at the bottom." />

## How is this different from sub-agents?

If you have used sub-agents in coding tools (including Suzent's own `explore`,
`plan`, `write`, `verify`, and `web` sub-agents), it is natural to ask: *isn't
Regent just a parent agent spawning sub-agents?*

No. They solve opposite problems at different layers of the stack:

- **Sub-agents protect an agent's context window.** When a *Coding* session
  needs to grep 200 files or run a noisy test suite, it spawns an ephemeral
  `explore` or `verify` sub-agent via the `agent` tool. The sub-agent does one
  bounded job, keeps the raw tool output out of the parent's prompt, returns a
  summary to that parent session, and terminates. You still had to open the
  *Coding* session and tell it what to do.
- **Regent protects *your* attention.** Regent sits *above* projects. It does
  not spawn throwaway workers for a single turn; it dispatches to durable
  **Project Primary Sessions** that own a folder, a `context.md` library, and a
  long-running task board — and those project sessions, in turn, spawn their own
  sub-agents while they work.

| Dimension | Sub-agents (`agent` tool) | Project Primary Sessions | Regent (`focal-suzent`) |
|---|---|---|---|
| **Core purpose** | Protect a session's context window & run parallel steps | Execute durable work inside one project | Protect **your attention** across all projects |
| **Scope** | Single task inside one parent session | One project (`context.md`, workspace, tasks) | Every active project in Suzent |
| **Lifespan** | Ephemeral (one bounded job, folded under parent in sidebar) | Long-lived conversation across days or weeks | Permanent singleton pinned at the top of the sidebar |
| **Who talks to it** | Its parent project session | Regent (via `agent_dispatch`) or you directly | **You** (and project sessions reporting back) |
| **Execution tools** | Scoped preset (`explore`, `write`, `verify`, `web`) | Full project toolset (files, bash, MCP, sub-agents) | **None** — orchestration & read-only lookup only |
| **Blocking behavior** | Can run synchronously or wake its parent session | Pauses on `ask_question`, tool approvals, or blocked tasks | Never waits on a turn; filters inbox events for you |

Put simply: **a project session uses sub-agents to divide labor; you use Regent
so you don't have to manage the project sessions.**

## Filter, not relay

Most multi-agent setups fail at the last mile: five agents do five things in
parallel and then reward you with five walls of text to read.

Regent's system prompt gives it a harder job: *"You are a filter, not a relay."*
Every event that reaches Regent's inbox — a reply to a dispatched task, a session
closing its last open task, or a task marked `blocked` on user input — passes
through two branches:

- **If a session blocks on a decision**, Regent surfaces one line: which project,
  what is stuck, and the exact choice it needs from you.
- **If a session finishes cleanly**, Regent replies with the quiet token
  (`HEARTBEAT_OK`). The event stays in Regent's history so it can answer
  questions about it later, but no desktop notification fires and the unread
  badge does not move.

<img src="/img/regent-filter-not-relay.svg" width="880" height="360" alt="Filter, not relay: a 4,000-character session transcript is distilled by Regent into a single decision line or suppressed via HEARTBEAT_OK." />

## Enforced boundaries, not polite prompts

If you give an orchestrator agent a bash tool and a file editor, it will
eventually stop orchestrating and start doing the work inline — polluting your
main conversation with half-finished diffs and command output.

Regent's boundaries are enforced in code before every turn
(`apply_focal_tool_policy()`):

- **Write and execution tools are stripped.** `FOCAL_TOOL_NAMES` equips only
  agent discovery/dispatch, memory/session search, web lookup, `ask_question`,
  read-only file tools, wake-up scheduling, and Regent's own notes tool. Every
  other tool is placed into `denied_tools` so it cannot even be discovered via
  tool search. MCP servers and working directories (`cwd`) are removed.
- **Zero-cost background check-ins.** Regent runs a built-in 30-minute heartbeat
  to spot sessions that have stalled with open tasks (idle for 30+ minutes) or
  blockers you haven't answered in two hours. Before calling any model, Suzent
  hashes the current findings in Python (`should_run_focal_heartbeat()`): if
  nothing is stuck or the state hasn't changed since the last check-in, the turn
  is skipped in code. A quiet afternoon costs zero tokens.

## Project isolation without context bleed

Because Regent never executes project work itself, each project keeps its own
working directory, task list, and `context.md` cleanly separated. Your coding
session's stack traces never leak into your research project's literature notes,
and neither clogs your conversation with Regent.

When you *do* want to inspect the raw work, Regent's board groups every project
session by where it stands for you — **waiting**, **running**, **idle**, or
**resolved** — and opening any session from the board gives you a one-click tag
in the header to jump straight back to Regent.

## A COO, not another chat tab

The right mental model for Regent is a Chief Operating Officer. You do not walk
from desk to desk checking who is stuck; you state the objective once, let the
teams work in their own rooms (with their own sub-agents), and expect to be
interrupted only when a call is genuinely yours to make.

Regent is a desktop feature today — the pinned sidebar card, the cross-project
board, and the `focal-suzent` conversation live in the desktop app. The
principle behind it is the core of how Suzent scales: **sub-agents scale a
session's execution; Regent scales your attention.**

---

[Quickstart](https://suzent.com/docs/getting-started/quickstart) ·
[Focal Agent Architecture](https://suzent.com/docs/developing/architecture/focal-agent) ·
[Source](https://github.com/cyzus/suzent) (Apache-2.0)
