# Suzent Automation Guide

This guide covers the automation systems in Suzent — scheduled cron jobs and periodic heartbeat check-ins.

## Overview

Suzent has two separate automation systems that allow it to act proactively without user-initiated requests:

| | Cron | Heartbeat |
|---|---|---|
| **Purpose** | Execute a specific task at a specific time | Periodic "wake up, check if anything needs attention" |
| **Session** | Isolated (`cron-{id}`) — fresh, stateless | Per-session — executes in the target chat's context |
| **Timing** | Cron expression (precise) | Fixed interval (default 30 min) |
| **Config** | Per-job prompt | Per-session `heartbeat.md` instructions |
| **Batching** | One job = one task | One tick can check multiple things |
| **Context** | No conversation history | Sees recent check history in that chat session |

**Use Cron when:** you want a scheduled action — daily reports, weekly summaries, timed reminders.

**Use Heartbeat when:** you want ambient monitoring — "check my inbox", "anything urgent?", "scan for problems". One heartbeat replaces many small cron jobs by batching checks in a single agent turn.

## Cron Jobs

### How It Works

1. You describe what you want automated and how often
2. Job is created via Settings > Automation, CLI, or through the agent
3. Scheduler fires the prompt in an isolated chat (`cron-{id}`)
4. Results delivered via status bar (announce) or silently logged (none)

Each cron job runs in its own isolated chat session with no conversation history. Memory is disabled to avoid polluting the knowledge base with routine output.

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

### Error Handling

- Failed jobs increment a retry counter
- After **5 consecutive failures**, the job is automatically deactivated
- Retry uses exponential backoff (base 60s)
- Check `last_error` in the UI or CLI to diagnose issues

### Managing Cron Jobs

#### Settings UI

Open **Settings > Automation** to:
- View scheduler status and job counts
- Create new jobs with name, cron expression, prompt, delivery mode, and model override
- Toggle jobs on/off, trigger immediate runs, or delete jobs
- View last run time, next run time, results, and errors

#### CLI

```bash
# List all jobs
suzent cron list [--verbose]

# Add a new job
suzent cron add --name "daily-summary" --cron "0 9 * * *" --prompt "Summarize today's agenda"

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

## Architecture

### Scheduler (Cron)

The `SchedulerBrain` follows the same singleton pattern as `SocialBrain`:

```
┌──────────────────┐
│  SchedulerBrain   │  tick every 30s
│  ._run_loop()     │──────────────────┐
└──────────────────┘                   │
                                       ▼
                              ┌─────────────────┐
                              │ Check due jobs   │
                              │ (next_run_at <=  │
                              │  now)            │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ _execute_job()   │
                              │ Isolated chat    │
                              │ cron-{job_id}    │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ Update DB state  │
                              │ Push notification│
                              └─────────────────┘
```

### Heartbeat

The `HeartbeatRunner` polls the database every 1 minute:

```
┌──────────────────┐
│  HeartbeatRunner  │  sleep(60s)
│  ._run_loop()     │──────────────────┐
└──────────────────┘                   │
                                       ▼
                              ┌─────────────────┐
                              │ Poll DB for     │
                              │ active sessions │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ Load config, run│
                              │ heartbeat for   │
                              │ due sessions    │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ HEARTBEAT_OK?   │
                              │ Yes → rollback  │
                              │ No → notify     │
                              └─────────────────┘
```

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
