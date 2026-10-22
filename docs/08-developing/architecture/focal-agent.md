---
sidebar_position: 12
---

# Focal Agent (Suzent Regent)

The Focal Agent is the singleton chat shown to users as **Suzent Regent**, or
**Regent** in the app. It sees every project, dispatches work to project
sessions, and is woken when one of them blocks on the user or finishes. It never
does project work itself. The code calls it "focal" throughout
(`suzent.core.focal_agent`); user-facing and model-facing text calls it Regent.

It was first shown as SUZENT. Existing installs pick up the new name without a
migration: the pinned title is restored on every `get_or_create_focal_chat()`,
and an untouched `heartbeat.md` or notes skeleton from then is upgraded through
`_PREVIOUS_FOCAL_HEARTBEATS` and `_PREVIOUS_FOCAL_NOTES`. The hidden project
keeps whatever name it was created with.

## Identity and storage

- One chat with the fixed ID `focal-suzent`, created on first use by
  `get_or_create_focal_chat()`. `is_focal_chat()` also accepts a chat whose
  config has `is_focal_agent: true` or `platform: "focal"`.
- It lives in the hidden system project `suzent-focal` (in
  `HIDDEN_PROJECT_SLUGS`), whose folder holds its `heartbeat.md`.
- Its title is pinned to `Regent`; auto-title skips it and
  `get_or_create_focal_chat()` restores the name if it changed.

## Tool policy

`apply_focal_tool_policy()` runs in `chat_processor` before every Focal turn
and overrides whatever the request asked for:

- `tools` is set to `FOCAL_TOOL_NAMES`: agent list/read/stop,
  `FocalDispatchTool`, web search and fetch, memory and session search,
  ask-question, skills, read-only file tools, `FocalScheduleTool`, and
  `FocalNotesTool`. The plain
  `AgentSendTool` is not in the set.
- Every other registered tool goes into `denied_tools`. Unequipped tools would
  otherwise still be reachable through ToolSearch.
- MCP is disabled, and `cwd` and `sandbox_volumes` are removed: project
  sessions carry their own working directory.
- `permission_mode` is `full_access`, since nothing in the set changes state
  outside Suzent.

Focal-only behavior lives in Focal-only tools, so other agents' schemas never
carry it. They sit together in `suzent.tools.focal`: `FocalDispatchTool`
(`agent_dispatch`, a subclass of `AgentSendTool`), `FocalScheduleTool`
(`schedule_wakeup`, a subclass of `ScheduleTool`) and `FocalNotesTool`
(`update_notes`). The two subclasses call their parents' internals, so a change
to `AgentSendTool._deliver` or `ScheduleTool`'s helpers needs a look there too.
All three have an empty `group` and are
not deferrable, so no other chat can equip or discover them, and all refuse
any chat that is not the Focal Agent. Their descriptions say "you" rather than
naming the Focal Agent, so nothing Regent reads calls it anything but Regent.

They need runtime names of their own: `is_denied()` resolves a runtime name to
one class through the registry, so a shared `agent_send` would be checked
against whichever class won the mapping.

## Global context

The `inject_focal_context` prompt layer (runtime) adds
`build_focal_global_context()` to Focal turns only: every non-archived project
with its id and slug, up to 10 sessions per project, and each session's tasks.
Sessions come from the project's tasks plus any chat in the project that is
running now, plus the 20 most recent sessions Regent started
(`parent_chat_id`), which may have no task. ACP sessions never do. Sessions
with work waiting on the user sort first, then running ones, and ACP sessions
are marked with their agent. Any other chat with no tasks that is not running
is not listed.

Each project line ends with one line from that project's `context.md`, read
live by `_project_overview()`: the first line of its Overview section, else its
first line of prose, cut at 160 characters. That gives Regent what each project
is about without a copy that could drift.

## Notes

Regent's notes are the `context.md` of `suzent-focal`, which core memory already
loads as the Context block for any chat in that project. Other chats keep their
project's `context.md` with the file tools; Regent has none, so
`FocalNotesTool` (`update_notes`) edits that one file and nothing else: an exact
`old_text` replacement, an entry added at the end of a `section` (created if
missing), or a plain append, capped at
`MAX_NOTES_CHARS` (8,000, where core memory starts truncating the block). An
edit reaches later turns as a core-memory diff reminder, like any other
context.md change.

`get_or_create_focal_chat()` seeds the file with `DEFAULT_FOCAL_NOTES`, a title
and empty sections, whenever it is missing. An existing file, even an empty
one, is left alone.

Regent has no library: it does no project work, so it produces no deliverables,
and `suzent-focal/` holds only its notes and `heartbeat.md`. Project knowledge
stays in each project's own `context.md`, maintained by that project's
sessions.

`format_core_memory_section()` swaps the "How to update your memory" lines for
the Focal chat: point at `update_notes`, and keep project and task status out,
since `build_focal_global_context()` supplies it fresh each turn. The tool's
`session_guidance` says what belongs in the notes.

## Dispatch

Both paths go through `FocalDispatchTool` and the
[agent inbox](./agent-inbox.md). It has no `wait` parameter and refuses
external A2A agents: Regent never holds a turn open on another agent, which
would also hold back the wake-ups and reports queued behind it.

- **Existing session:** `agent_dispatch(agent_id=<chat id>, message=...)`.
  `watch_session()` sets `focal_watching` on the target so Focal hears when it
  finishes.
- **New session:** `agent_dispatch(agent_id="new", project_id=..., title=...,
  task_title=..., message=...)`. It creates
  a chat in the project with `permission_mode: "auto"` (Smart),
  `parent_chat_id` and `spawned_by_focal`, binds an `in_progress` task when
  `task_title` is given, and enqueues the message. The desktop renders that
  first `system_triggered` message as a user message (`focalRequestText`), so
  the session shows what it was asked.
- **New ACP session:** the same call with `acp_agent_id` (from
  `agent_list(status="acp")`, which tells Regent to use `agent_dispatch` rather
  than `agent`). The chat gets `runtime: "acp"` and `acp_agent_id`, so the inbox
  delivers through `run_acp_turn_text()` with the project folder as its
  working directory. Its `permission_mode` is `default`, not `auto`: for ACP,
  `auto` allows every request outright (`acp/permissions.py`), with no reviewer
  behind it. The inbox runs each ACP turn on a background stream, as ACP
  sub-agents do, so opening the session attaches to it and shows any pending
  approval. A request nobody answers fails closed after the broker's timeout.
  If the turn fails before saying anything (the agent isn't signed in, the
  handshake fails), `run_acp_turn_text(errors_out=...)` hands the inbox the
  `RUN_ERROR`, and the reply becomes "The ACP agent could not run this: …".
  Otherwise the empty reply would be dropped and Regent would never hear.
  `task_title` is refused, because an ACP agent can't update Suzent tasks and
  the task would stay `in_progress`, and the heartbeat would flag it as stalled.
  An unknown or uninstalled agent is refused before anything is created.
- **Paired Suzent:** `agent_dispatch(agent_id="peer:...")` goes through the
  peer outbox in `_deliver()`, asynchronously like any other message.

## Hearing back

Three events enqueue an inbox message to `focal-suzent`:

| Event | Source | Inbox `kind` |
|---|---|---|
| A session answers a message Focal sent it | `route_focal_reply()` from the inbox worker; replies over 4,000 characters are truncated | `agent_message` |
| A task becomes blocked on `user` or `error`, or its reason changes | `notify_focal_of_blocked_task()` from `TaskUpdateTool` | `task_blocked_notification` |
| A followed session closes its last open task | `notify_focal_of_finished_session()` from `TaskUpdateTool`, skipped while a Focal request to it is still in flight | `session_finished_notification` |

Any session may also message Regent itself with `agent_send`
(`_sendable_agent()`), but `agent_read` and `agent_stop` don't reach it: its
conversation spans every project.

A session counts as followed when Focal started it (`parent_chat_id`) or sent
it work (`focal_watching`). Blocked-task notices go to Focal for any session,
but only once the Focal chat exists; they never create it for a user who has
not opened Regent, except for sessions Focal started.

When a woken Focal turn replies, `announce_focal_reply()` also queues a
desktop notification, since the user may not have the chat open.

## Heartbeat

The first `get_or_create_focal_chat()` enables the heartbeat at 30 minutes
and seeds `heartbeat.md` with `DEFAULT_FOCAL_HEARTBEAT`, once
(`focal_heartbeat_initialized`). After that the setting belongs to the user.
A checklist still identical to an earlier built-in one
(`_PREVIOUS_FOCAL_HEARTBEATS`) is upgraded in place; an edited one is never
touched.

To keep a quiet heartbeat free, `should_run_focal_heartbeat()` decides in code
before any model call:

- A user-edited checklist always runs.
- The default checklist runs only when `_heartbeat_findings()` is non-empty
  and its SHA-256 signature differs from `focal_heartbeat_signature`. Findings
  are sessions idle for 30 minutes with open tasks and nothing waiting on the
  user (`STALL_AFTER`), and blockers unanswered for 2 hours
  (`REMIND_BLOCKED_AFTER`).
- A skipped run is recorded as run (`record_skipped_heartbeat()`), so the
  schedule advances a full interval.

The signature is written by `record_focal_heartbeat_done()` only after a
check-in turn succeeds, so a failed or preempted check-in raises the same
findings next time.

## Wake-ups

`schedule_wakeup` creates agent-sourced cron jobs on the Focal chat, at most
20. `kind="reminder"` always notifies; `kind="check"` sets `suppress_ok`, so
the user hears only when there is something to say. Focal wake-ups always run
inside the Focal chat under its own tool policy: there is no isolated variant,
which would run with a full tool set.

## HTTP API

| Route | Purpose |
|---|---|
| `GET /focal` | Create the chat if needed and return `focal_status()`: waiting, stalled and auto-running counts, per-project and per-chat waiting counts, unread count and last message |
| `GET /focal/panel` | The fixed tool list and scheduled wake-ups, for the Tools tab |
| `DELETE /focal/wakeups/{job_id}` | Cancel one of Focal's own wake-ups; any other job id is refused |

## Desktop

- `FocalAgentCard` at the top of the sidebar, fed by `useFocalStatus`.
- `FocalBriefing` replaces the empty-chat screen with a greeting and the
  sessions that need attention.
- The Tasks panel on the Focal chat shows the all-projects board grouped by
  session, with a remembered project filter.
- The Tools tab shows `FocalToolsPanel` instead of the tool picker, and the
  input hides the folder and attachment controls.
