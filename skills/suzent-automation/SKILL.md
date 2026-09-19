---
name: suzent-automation
description: Create, inspect, update, trigger, or troubleshoot Suzent scheduled tasks — cron jobs, interval polling, one-shot reminders, and per-chat heartbeat checks. Use for recurring reports, follow-ups, periodic monitoring, and heartbeat configuration.
---

# Automation

Everything Suzent runs on a schedule is one thing: a **scheduled task**. A task
answers two questions independently.

**When does it fire?**

| Kind | Timing | Use for |
|---|---|---|
| cron | A cron expression, optionally in a named timezone | Wall-clock work — daily reports, weekday summaries |
| interval | A fixed gap in minutes | Ambient polling — "check every 30 minutes" |
| once | A single timestamp | Follow-ups — "look at this again in 20 minutes" |

**Where does it run?**

| Mode | Runs in | Trade-off |
|---|---|---|
| isolated | A dedicated `cron-{id}` chat | Cheap and self-contained. It sees only its own prior runs, so the prompt must carry everything it needs. |
| bound | An existing conversation | It sees that conversation and can continue it. Costs the history in tokens every run, and waits its turn while someone is typing. |

A **heartbeat** is a task too: interval-scheduled, bound, and quiet. It is
configured separately (see below) because its checklist lives in a file.

Do not create or modify automation when the user is only asking how scheduling
works.

## Scheduling your own follow-up

When *you* need to come back to something — a build that is still running, a
review you are waiting on — use the `schedule_task` tool rather than the CLI. It
defaults to binding to the current conversation, so the task wakes up with this
context intact.

```text
schedule_task(action="create", name="recheck CI", prompt="...", in_minutes=20)
schedule_task(action="list")
schedule_task(action="cancel", task_id=7)
```

Give exactly one of `in_minutes`, `at`, `every_minutes` or `cron`. Write `prompt`
for your future self: state the goal and how to tell you are done.

Bounds, because a task you schedule wakes you and you could schedule another:

- at most **5** of your own tasks per chat — cancel one before adding another
- repeating schedules fire no more often than every **5 minutes** (checked
  across the whole cron cycle, not just the next two fires)
- delays are at least **1 minute**

You can only change or cancel tasks you created. A heartbeat or a cron job the
user set up is theirs — ask rather than editing it.

`bind_to_chat=False` runs the task in its own chat instead. Prefer that when the
prompt stands alone: it keeps the cost flat however long this conversation grows.

### Quiet tasks

A bound task defaults to `quiet_if_nothing_to_report=True`. When it fires, reply
with exactly `HEARTBEAT_OK` and nothing else if there is nothing worth saying —
that turn is then removed and the conversation is left untouched. Answer normally
only when something needs attention; that answer is written into the conversation
under a `Scheduled Task:` header.

## Managing tasks the user owns

Use the `suzent cron` CLI through `RunCommandTool` in host mode:

```text
suzent cron list --verbose
suzent cron add --name "daily-summary" --cron "0 9 * * *" --prompt "Summarize today's agenda"
suzent cron add --name "poll-ci" --every 15 --prompt "Check the build"
suzent cron add --name "follow-up" --at "2026-01-02T09:00" --prompt "Revisit the migration"
suzent cron add --name "watch-pr" --every 30 --chat <chat_id> --quiet --prompt "Has CI finished?"
suzent cron trigger <job_id>
suzent cron toggle <job_id>
suzent cron remove <job_id>
suzent cron status
```

Exactly one of `--cron`, `--every` or `--at` is required. `--chat` binds the task
to a conversation; `--quiet` then leaves that conversation untouched when the run
has nothing to report. `--timezone`, `--jitter` and `--catch-up` tune the timing
(see below).

In sandbox mode, use `$SUZENT_BASE_URL` and the local API:

| Action | Method | Path |
|---|---|---|
| List | `GET` | `/cron/jobs` |
| Create | `POST` | `/cron/jobs` |
| Update | `PUT` | `/cron/jobs/{id}` |
| Delete | `DELETE` | `/cron/jobs/{id}` |
| Trigger | `POST` | `/cron/jobs/{id}/trigger` |
| Status | `GET` | `/cron/status` |

Create with `name`, `prompt`, and a schedule: `schedule_kind` plus `cron_expr`,
`interval_minutes`, or `run_at`. Add `chat_id` with `context_mode: "bound"` to
bind it. Set `delivery_mode` to `announce` for a status notification or `none`
for silent history-only execution.

## Timing policy

Three fields shape when a fire actually lands:

- `timezone` — evaluate a cron expression in a named IANA zone. Without it the
  task follows the machine's local time, which shifts under the machine.
- `jitter_seconds` — spread the fire over a random window, so a dozen tasks
  sharing `0 9 * * *` do not all wake at once.
- `catch_up` — what to do about runs missed while the machine slept. `skip`
  (default) drops anything overdue by more than one period; `run_once` makes up
  a single run. A one-shot is never skipped, however late.

## Failures

Failures retry with exponential backoff up to five times; a further failure
deactivates the task. A bound task that finds its chat mid-turn is **not** a
failure — it slides to the next tick and spends no retry, so binding a task to a
chat someone actively uses is fine. Still avoid schedules shorter than the task's
normal duration.

## Heartbeat

Heartbeat keeps its own configuration: enabled per chat, with its checklist in
that chat's `heartbeat.md`. At most one chat per project may have it on. It shows
up in Settings → Automation as a read-only row, because the scheduler keeps that
row in sync with the chat's own settings.

Use the sidebar for interactive configuration or these host-mode commands:

```text
suzent heartbeat status -c <chat_id>
suzent heartbeat enable -c <chat_id>
suzent heartbeat disable -c <chat_id>
suzent heartbeat run -c <chat_id>
suzent heartbeat interval <minutes> -c <chat_id>
```

Sandbox API routes:

| Action | Method | Path |
|---|---|---|
| Status | `GET` | `/heartbeat/status?chat_id={id}` |
| Enable | `POST` | `/heartbeat/enable` |
| Disable | `POST` | `/heartbeat/disable` |
| Trigger | `POST` | `/heartbeat/trigger` |
| Interval | `POST` or `PUT` | `/heartbeat/interval` |

Keep `heartbeat.md` short and observable. Describe what to inspect, what
qualifies as actionable, and what evidence to report. Do not tell heartbeat to
repeat old alerts or perform destructive/external actions without the normal
permission policy.

## Memory

Scheduled tasks enable memory context. Do not assume a memory-search tool is
equipped, and do not write automation prompts that depend on unspecified
memories.
