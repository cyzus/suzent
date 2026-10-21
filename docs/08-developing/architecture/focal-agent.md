---
sidebar_position: 12
---

# Focal Agent (SUZENT)

The Focal Agent is the singleton chat shown to users as **SUZENT**. It sees
every project, dispatches work to project sessions, and is woken when one of
them blocks on the user or finishes. It never does project work itself. The
code calls it "focal" throughout (`suzent.core.focal_agent`); user-facing text
calls it SUZENT and gives it no role name.

## Identity and storage

- One chat with the fixed ID `focal-suzent`, created on first use by
  `get_or_create_focal_chat()`. `is_focal_chat()` also accepts a chat whose
  config has `is_focal_agent: true` or `platform: "focal"`.
- It lives in the hidden system project `suzent-focal` (in
  `HIDDEN_PROJECT_SLUGS`), whose folder holds its `heartbeat.md`.
- Its title is pinned to `SUZENT`; auto-title skips it and
  `get_or_create_focal_chat()` restores the name if it changed.

## Tool policy

`apply_focal_tool_policy()` runs in `chat_processor` before every Focal turn
and overrides whatever the request asked for:

- `tools` is set to `FOCAL_TOOL_NAMES`: agent list/read/send/stop, web search
  and fetch, memory and session search, ask-question, skills, read-only file
  tools, and `FocalScheduleTool`.
- Every other registered tool goes into `denied_tools`. Unequipped tools would
  otherwise still be reachable through ToolSearch.
- MCP is disabled, and `cwd` and `sandbox_volumes` are removed: project
  sessions carry their own working directory.
- `permission_mode` is `full_access`, since nothing in the set changes state
  outside Suzent.

`FocalScheduleTool` (`schedule_wakeup`) has an empty `group` and is not
deferrable, so no other chat can equip or discover it, and it refuses any chat
that is not the Focal Agent.

## Global context

The `inject_focal_context` prompt layer (runtime) adds
`build_focal_global_context()` to Focal turns only: every non-archived project
with its id and slug, up to 10 sessions per project, and each session's tasks.
Sessions come from the project's tasks plus any chat in the project that is
running now; sessions with work waiting on the user sort first, then running
ones. A chat with no tasks that is not running is not listed.

## Dispatch

Both paths go through `AgentSendTool` and the [agent inbox](./agent-inbox.md):

- **Existing session:** `agent_send(agent_id=<chat id>, message=...)`.
  `watch_session()` sets `focal_watching` on the target so Focal hears when it
  finishes.
- **New session:** `agent_send(agent_id="new", project_id=..., title=...,
  task_title=..., message=...)`, allowed only from the Focal Agent. It creates
  a chat in the project with `permission_mode: "auto"` (Smart),
  `parent_chat_id` and `spawned_by_focal`, binds an `in_progress` task when
  `task_title` is given, and enqueues the message. The desktop renders that
  first `system_triggered` message as a user message (`focalRequestText`), so
  the session shows what it was asked.

## Hearing back

Three events enqueue an inbox message to `focal-suzent`:

| Event | Source | Inbox `kind` |
|---|---|---|
| A session answers a message Focal sent it | `route_focal_reply()` from the inbox worker; replies over 4,000 characters are truncated | `agent_message` |
| A task becomes blocked on `user` or `error`, or its reason changes | `notify_focal_of_blocked_task()` from `TaskUpdateTool` | `task_blocked_notification` |
| A followed session closes its last open task | `notify_focal_of_finished_session()` from `TaskUpdateTool`, skipped while a Focal request to it is still in flight | `session_finished_notification` |

A session counts as followed when Focal started it (`parent_chat_id`) or sent
it work (`focal_watching`). Blocked-task notices go to Focal for any session,
but only once the Focal chat exists; they never create it for a user who has
not opened SUZENT, except for sessions Focal started.

When a woken Focal turn replies, `announce_focal_reply()` also queues a
desktop notification, since the user may not have the chat open.

## Heartbeat

The first `get_or_create_focal_chat()` enables the heartbeat at 30 minutes
and seeds `heartbeat.md` with `DEFAULT_FOCAL_HEARTBEAT`, once
(`focal_heartbeat_initialized`). After that the setting belongs to the user.

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
