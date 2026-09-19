# Suzent Automation Guide

**Sovereign authority.** Proactive action is the sharpest edge of agent
autonomy: work that happens when you are not watching. Every scheduled task below
runs on a schedule and instructions you write. None of them inherit the permission
mode of the chat they were scheduled from — including a task bound to that chat:
background turns always run in Auto mode under a
headless profile, where an action that cannot be classified as safe is denied
rather than queued for an approval nobody is present to give. See
[Headless Runs](https://suzent.com/docs/concepts/tools/human-in-the-loop#headless-runs)
for what that permits, and [what makes an agent sovereign](https://suzent.com/sovereign).

This guide covers scheduled tasks in Suzent — cron jobs, interval polling, one-shot
reminders, and the heartbeat check-ins that are a special case of them.

## Overview

Everything Suzent does on a schedule is one kind of thing: a **scheduled task**.
A task answers two questions independently.

**When does it fire?** (`schedule_kind`)

| Kind | Timing | Use for |
|---|---|---|
| `cron` | A cron expression, optionally in a named timezone | Wall-clock work — daily reports, weekday summaries |
| `interval` | A fixed gap in minutes | Ambient polling — "check every 30 minutes" |
| `once` | A single `run_at` timestamp | Reminders and follow-ups — "look at this again in 20 minutes" |

**Where does it run?** (`context_mode`)

| Mode | Runs in | Trade-off |
|---|---|---|
| `isolated` | A dedicated chat, `cron-{id}` | Cheap and self-contained. The task sees only its own prior runs, so the prompt has to carry everything it needs. |
| `bound` | An existing conversation | The task sees that conversation and can continue it. Costs the full history in tokens on every run, and has to wait its turn while you are typing. |

A **heartbeat** is not a separate system: it is a task that is `interval`-scheduled,
`bound` to a chat, and marked to roll itself back when it has nothing to report.
Its checklist lives in that project's `heartbeat.md` rather than in the task's
prompt, and it keeps one delivery quirk of its own (see [Heartbeat](#heartbeat)).

A bound task is either **quiet** or not, and the two behave differently on
purpose. A quiet task is asked to answer with the exact `HEARTBEAT_OK` token
when it has nothing to report; that turn is then rolled back, and nothing it
did reaches the transcript. A task that is not quiet joins the conversation
like any other turn — that is what makes it worth binding, since its answer is
meant to be read there.

When a quiet task *does* have something to report, the answer is written into
the conversation under a `Scheduled Task: <name>` header — after it has been
classified, never before. That ordering is the whole trick: a turn is never
sitting in the transcript waiting on a rollback that a failure could stop from
running. If someone happened to be watching the chat while it ran, the
streamed turn is already there and nothing is written twice.

**Reach for a bound task when** the work only makes sense against a conversation:
rechecking something you and the agent were just looking at, or monitoring a
situation the chat already explains. **Reach for an isolated task when** the
prompt can stand alone — that keeps the cost flat no matter how long the
conversation grows.

## Cron Jobs

### How It Works

1. You describe what you want automated and how often
2. Job is created via Settings > Automation, CLI, or through the agent
3. Scheduler fires the prompt — in an isolated chat (`cron-{id}`) by default, or
   in the chat you bound it to
4. Results delivered via status bar (announce) or silently logged (none)

An isolated job runs in its own dedicated persistent chat. Later runs can see that chat's
prior agent state, although prompts should remain self-contained. Cron and heartbeat
currently enable memory context; availability of memory-search tools is configured
separately.

### Cron Expression Reference

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```

Common patterns:

| Expression | Schedule |
|---|---|
| `*/5 * * * *` | Every 5 minutes |
| `0 * * * *` | Every hour |
| `0 9 * * *` | Daily at 9:00 AM |
| `0 9 * * 1-5` | Weekdays at 9:00 AM |
| `0 9,18 * * *` | Twice daily at 9 AM and 6 PM |
| `0 0 * * 0` | Weekly on Sunday at midnight |
| `0 0 1 * *` | First day of each month |

### Delivery Modes

| Mode | Behavior |
|---|---|
| `announce` | Result appears in the status bar notification |
| `none` | Result is logged silently (check via UI or CLI) |

### Timing Policy

Three fields shape *when* a fire actually happens, beyond the schedule itself.

| Field | Effect |
|---|---|
| `timezone` | Evaluates a cron expression in a named IANA zone. Without it, tasks follow the machine's local time, which shifts under the machine. |
| `jitter_seconds` | Spreads the fire time over a random window, so a dozen tasks sharing `0 9 * * *` don't all wake at once. |
| `catch_up` | What to do about runs missed while the machine slept. `skip` (default) drops anything overdue by more than one full period; `run_once` makes up a single run instead. |

A one-shot task is never skipped, however late it is: a reminder that arrives
late is still worth having, and there is no next occurrence to defer to.

### Error Handling

- Failed jobs increment a retry counter
- After **5 consecutive failures**, the job is automatically deactivated
- Retry uses exponential backoff (base 60s)
- Check `last_error` in the UI or CLI to diagnose issues

A bound task that finds its chat mid-turn is **not** a failure. It slides to the
next tick without touching the retry counter — otherwise five turns of ordinary
conversation would deactivate it.

### Tasks the Agent Schedules

The agent can schedule its own follow-ups with the `schedule_task` tool, which
defaults to binding to the conversation it is called from:

> "The deploy is running. I'll check back in 15 minutes."

Because a task the agent schedules wakes the agent, which could schedule
another, the tool is bounded: at most **5** agent-created tasks per chat, a
**5 minute** floor on repeating schedules, and a **1 minute** floor on delays.
The agent can only cancel or edit tasks it created itself — a heartbeat or a
cron job you set up is yours, and it has to ask.

### Managing Cron Jobs

#### Settings UI

Open **Settings > Automation** to:
- View scheduler status and job counts
- Create tasks on any schedule — every N minutes, hourly, daily, weekly, monthly,
  once at a timestamp, or a raw cron expression
- Pin a cron schedule to a timezone, add jitter, and choose a catch-up policy
- Pick **Runs in**: its own isolated chat, or an existing conversation. A bound
  task can be told to stay quiet when it has nothing to report, leaving the
  conversation untouched
- Toggle jobs on/off, trigger immediate runs, or delete jobs
- View last run time, next run time, results, and errors

Heartbeat rows appear in this list too, marked `heartbeat`, but are read-only
here: the scheduler keeps them in sync with the chat's own settings, so an edit
made here would be reconciled away. Change a heartbeat from that chat's
**Config** tab instead.

#### CLI

```bash
# List all jobs
suzent cron list [--verbose]

# Add a new job
suzent cron add --name "daily-summary" --cron "0 9 * * *" --prompt "Summarize today's agenda"

# Repeat on an interval, or run once at a timestamp
suzent cron add --name "poll-ci" --every 15 --prompt "Check the build"
suzent cron add --name "follow-up" --at "2026-01-02T09:00" --prompt "Revisit the migration"

# Run inside an existing chat so the task can see the conversation.
# --quiet leaves the chat untouched when the run has nothing to report.
suzent cron add --name "watch-pr" --every 30 --chat <chat_id> --quiet \
  --prompt "Has CI finished on the PR we were discussing?"

# Spread the wake-up, and pin a cron expression to a timezone
suzent cron add --name "report" --cron "0 9 * * *" --timezone Asia/Shanghai --jitter 120 \
  --prompt "Morning report"

# Trigger a job immediately
suzent cron trigger <job_id>

# Toggle a job on/off
suzent cron toggle <job_id>

# Remove a job
suzent cron remove <job_id>

# Show scheduler status
suzent cron status
```

#### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cron/jobs` | List all jobs |
| POST | `/cron/jobs` | Create a job |
| PUT | `/cron/jobs/{job_id}` | Update a job |
| DELETE | `/cron/jobs/{job_id}` | Delete a job |
| POST | `/cron/jobs/{job_id}/trigger` | Trigger immediate run |
| GET | `/cron/status` | Scheduler health and job counts |
| GET | `/cron/notifications` | Drain pending announce notifications |

## Heartbeat

### How It Works

1. Enable the heartbeat system directly in the left sidebar **Config** tab of any chat
2. Configure your specific `heartbeat.md` instructions directly in the chat's sidebar
3. HeartbeatRunner fires at the configured interval (default 30 minutes) and executes those instructions
4. Agent reads the checks, processes tasks
5. If nothing needs attention, agent replies `HEARTBEAT_OK` and the turn is rolled back (suppressed) to avoid clogging your chat history
6. If something is actionable, it surfaces via the status bar or the chat

Unlike cron jobs, the heartbeat executes in an **existing persistent chat session** allowing it to access previous interactions and context specific to that chat.

### heartbeat.md Instructions

The checklist settings live directly inside the chat configuration of the session, rather than a global file.

Example checklist:

```markdown
# Heartbeat Checklist

- Quick scan: anything urgent in recent conversations?
- If a task was left incomplete, note what is missing.
- Check for any pending follow-ups.
```

#### Editing heartbeat.md

1. **Sidebar UI** — Open the specific chat session, click the **Config** tab in the left sidebar, and edit the `heartbeat.md instructions` directly.

#### Rules for the Agent During Heartbeat

- Follow the checklist strictly
- Do not infer or repeat old tasks from prior heartbeats
- Reply `HEARTBEAT_OK` if nothing needs attention
- Keep responses concise — only surface actionable items

### HEARTBEAT_OK Suppression

When the agent determines nothing needs attention, it replies with `HEARTBEAT_OK`. This response is suppressed from notifications to avoid noise. The suppression logic tolerates minor preamble text (up to 300 extra characters) around the sentinel.

### Managing Heartbeat

#### Sidebar UI

The "Session Heartbeat" section in a chat's **Config** sidebar allows you to:
- Toggle the heartbeat on or off
- Configure the wait interval (in minutes)
- Edit the session's specific `heartbeat.md`
- See the last run time and trigger an immediate run

#### CLI

```bash
# Show heartbeat status for a session
suzent heartbeat status -c <chat-id>

# Enable heartbeat for a session
suzent heartbeat enable -c <chat-id>

# Disable heartbeat
suzent heartbeat disable -c <chat-id>

# Set the heartbeat interval (in minutes)
suzent heartbeat interval 15 -c <chat-id>

# Trigger an immediate heartbeat tick
suzent heartbeat run -c <chat-id>
```

#### REST API

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/heartbeat/status` | Heartbeat system status |
| POST | `/heartbeat/enable` | Enable heartbeat |
| POST | `/heartbeat/disable` | Disable heartbeat |
| POST | `/heartbeat/trigger` | Trigger immediate tick |
| GET | `/heartbeat/md` | Read HEARTBEAT.md content |
| PUT | `/heartbeat/md` | Update HEARTBEAT.md content |
| PUT | `/heartbeat/interval` | Set interval (`{"interval_minutes": N}`) |

## Goal Mode

Goal mode lets the agent pursue a standing objective across many turns without
you re-prompting each step — our take on the "Ralph loop". Use it for tasks
where "done" is well-defined and you want to walk away, e.g. *"Fix every lint
error in `src/` and verify `ruff check` passes"*.

### How It Works

1. You set a goal with `/goal <objective>`. The agent immediately starts working on it (turn 1).
2. After each turn, an auxiliary **judge** model (a single, cheap, stateless LLM call — not a full agent) decides whether the goal is fully satisfied.
3. If not, and the turn budget isn't exhausted, the agent is automatically run again with a continuation prompt — you'll see `↻ Continuing toward goal (N/max)` in the status bar.
4. When the judge says the goal is met, you see `✓ Goal achieved: <reason>`. When the budget runs out, you see `⏸ Goal paused — N/max turns used`.
5. **Any real message you send preempts the loop** — your turn runs first, then the judge re-evaluates from there.

Goals are stored in the project `GoalModel` (project + chat scoped) — the same
record the agent's `manage_goal` tool writes and the **right-sidebar Goal tab**
displays (objective, status, turn progress, sub-goals). The sidebar also exposes
**Pause / Resume / Clear** buttons (via `POST /project/goal/action`) so you can
control the loop without typing a command — Resume re-enters the continuation
loop exactly like `/goal resume`. Setting a goal lights up the sidebar
automatically, and state survives restarts and resumes. The per-turn
`plan_reminder_hook` injects the active goal into context and advances the turn
counter; this judge loop layers automatic continuation on top of that.

The judge **fails open**: if the judge call errors or returns something
unparseable, the loop continues (the turn budget is the real safety backstop).
After 3 consecutive unparseable verdicts the goal auto-pauses and asks you to
configure a stronger `cheap` role model.

Autonomous goal turns auto-approve tools so the agent can act unattended.

### Commands

| Command | Action |
|---|---|
| `/goal <objective>` | Set a goal and start working toward it |
| `/goal` or `/goal status` | Show the current goal, status, and turn progress |
| `/goal pause` | Stop the auto-continuation loop |
| `/goal resume` | Resume a paused goal (resets the turn counter) |
| `/goal clear` | Remove the goal |
| `/subgoal <text>` | Append an acceptance criterion (judge requires all sub-goals met) |
| `/subgoal` | List current sub-goals |
| `/subgoal remove <N>` | Remove sub-goal number `N` |
| `/subgoal clear` | Remove all sub-goals |

### Configuration

| Setting | Default | Description |
|---|---|---|
| `goals_max_turns` | `20` | Max autonomous continuation turns before auto-pausing |

The judge uses the `cheap` model role (configurable in **Settings → Model
Roles**), falling back to the primary model if `cheap` is unset.

## Architecture

There is **one clock and one table**. `SchedulerBrain` owns the timing for every
scheduled task, including heartbeats; `HeartbeatRunner` owns execution inside a
live conversation. Tasks live in the `cron_jobs` table, which kept its name from
when cron was all there was.

```
┌──────────────────┐
│  SchedulerBrain   │  tick every 30s
│  ._tick()         │
└─────────┬────────┘
          │  1. project heartbeat-enabled chats onto task rows
          │  2. find rows with next_run_at <= now
          │     (skipping in-flight rows and stale missed runs)
          ▼
   ┌──────────────┐
   │ context_mode │
   └──┬────────┬──┘
      │        │
 isolated    bound ──── chat busy? ──► slide to next tick, no retry spent
      │        │
      ▼        ▼
┌───────────┐ ┌──────────────────────────────┐
│ cron-{id} │ │ HeartbeatRunner              │
│ chat, via │ │  .run_bound_turn()           │
│ ChatProc- │ │  background turn in the chat │
│ essor     │ │  suppress_ok → roll back a   │
└─────┬─────┘ │  turn with nothing to report │
      │       └───────────────┬──────────────┘
      └───────────┬───────────┘
                  ▼
        ┌──────────────────┐
        │ Record the run   │
        │ Re-arm or retire │
        │ Notify if asked  │
        └──────────────────┘
```

Heartbeat rows take one detour: instead of running straight away, the scheduler
marks the chat **pending** and the runner gives an attached frontend 20 seconds
to claim the turn and stream it where you can watch. Nobody claims it, the
server runs it headlessly. That is why heartbeats produce no run history and no
notification — they are not reportable task runs.

Heartbeat stays configured where the UI already writes it (`chat.config` plus the
project's `heartbeat.md`); each tick reconciles that with the task row in both
directions, so changing the interval re-arms the row, and a heartbeat the
frontend ran itself pushes the row's next fire time out.

### Notification Flow

Both systems deliver notifications through a shared mechanism:

1. Cron jobs with `delivery_mode: "announce"` push results to an in-memory deque
2. Heartbeat alerts route through the scheduler's notification deque via a callback
3. Frontend polls `GET /cron/notifications` every 5 seconds
4. Notifications appear in the status bar

## Configuration

### Server Lifecycle

Both systems start during server initialization (`init_background_services()`) and stop during shutdown:

- **SchedulerBrain** — ticks every 30 seconds, checking for due jobs
- **HeartbeatRunner** — sleeps for the configured interval (default 30 minutes)

### Model Resolution

Both systems resolve which LLM model to use in this order:

1. Job-level `model_override` (cron only)
2. User preferences model (from settings)
3. System default

### Memory

Memory is **disabled** for both cron and heartbeat executions to avoid polluting the knowledge base with routine automated output.

## Troubleshooting

### Scheduler Not Running

**Problem:** `GET /cron/status` shows `scheduler_running: false`

**Solutions:**
1. Check server logs for startup errors
2. Verify `croniter` is installed (`pip show croniter`)
3. Restart the server

### Job Never Fires

**Problem:** Job exists but `last_run_at` stays null

**Solutions:**
1. Check `active` is `true`
2. Verify cron expression is valid
3. Check `next_run_at` — is it in the future?
4. Look for errors in server logs

### Job Deactivated After Failures

**Problem:** Job was auto-deactivated after 5 failures

**Solutions:**
1. Check `last_error` for the failure reason
2. Fix the underlying issue (model auth, prompt errors, etc.)
3. Re-enable the job via toggle in UI or `suzent cron toggle <id>`

### Heartbeat Won't Run

**Problem:** Heartbeat is enabled, but nothing happens

**Solutions:**
1. Check the server logs (with `--debug` enabled) to ensure HeartbeatRunner is polling
2. Verify your chat interval has passed
3. If it outputs HEARTBEAT_OK, it successfully ran but rolled itself back (this is intended behavior to avoid contextual bloat)

### HEARTBEAT_OK Not Suppressing

**Problem:** Getting notifications even when agent says HEARTBEAT_OK

**Solutions:**
1. Ensure the agent's response contains exactly `HEARTBEAT_OK` (case-sensitive)
2. Extra text around the sentinel must be under 300 characters
3. Check that the response isn't wrapped in markdown formatting
