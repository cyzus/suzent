# Suzent Automation Guide

This guide covers the automation systems in Suzent — scheduled cron jobs and periodic heartbeat check-ins.

## Overview

Suzent has two separate automation systems that allow it to act proactively without user-initiated requests:

| | Cron | Heartbeat |
|---|---|---|
| **Purpose** | Execute a specific task at a specific time | Periodic "wake up, check if anything needs attention" |
| **Session** | Isolated (`cron-{id}`) — fresh, stateless | Persistent (`heartbeat-main`) — accumulates context |
| **Timing** | Cron expression (precise) | Fixed interval (default 30 min) |
| **Config** | Per-job prompt | Single `/shared/HEARTBEAT.md` checklist |
| **Batching** | One job = one task | One tick can check multiple things |
| **Context** | No conversation history | Sees recent check history |

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

1. Create a checklist at `/shared/HEARTBEAT.md` (via Settings > Automation editor or file tools)
2. Enable the heartbeat system
3. HeartbeatRunner fires at a configurable interval (default 30 minutes) in a persistent `heartbeat-main` chat
4. Agent reads the checklist, checks each item
5. If nothing needs attention, agent replies `HEARTBEAT_OK` (notification suppressed)
6. If something is actionable, it surfaces via the status bar

Unlike cron jobs, the heartbeat runs in a **persistent chat session** that accumulates context across ticks. This means the agent can see what it checked previously and avoid repeating stale information.

### HEARTBEAT.md

The checklist lives at `/shared/HEARTBEAT.md`, alongside the memory workspace (`/shared/memory/`). This location allows both the agent and the frontend to read and edit it.

Example checklist:

```markdown
# Heartbeat Checklist

- Quick scan: anything urgent in recent conversations?
- If a task was left incomplete, note what is missing.
- Check for any pending follow-ups.
```

An example template is provided at `config/HEARTBEAT.example.md`.

#### Editing HEARTBEAT.md

There are three ways to edit the checklist:

1. **Settings UI** — Open Settings > Automation, expand the HEARTBEAT.md editor in the heartbeat card
2. **Agent** — Ask the agent to edit `/shared/HEARTBEAT.md` using file tools
3. **CLI/File system** — Edit the file directly at `{sandbox_data_path}/shared/HEARTBEAT.md`

#### Rules for the Agent During Heartbeat

- Follow the checklist strictly
- Do not infer or repeat old tasks from prior heartbeats
- Reply `HEARTBEAT_OK` if nothing needs attention
- Keep responses concise — only surface actionable items

### HEARTBEAT_OK Suppression

When the agent determines nothing needs attention, it replies with `HEARTBEAT_OK`. This response is suppressed from notifications to avoid noise. The suppression logic tolerates minor preamble text (up to 300 extra characters) around the sentinel.

### Managing Heartbeat

#### Settings UI

The heartbeat card in **Settings > Automation** shows:
- Current status (enabled/disabled/running)
- Configurable interval (editable inline) and whether HEARTBEAT.md exists
- Enable/Disable toggle and Run Now button
- Inline HEARTBEAT.md editor
- Last run time, result, and errors

#### CLI

```bash
# Show heartbeat status
suzent heartbeat status

# Enable heartbeat (requires HEARTBEAT.md to exist)
suzent heartbeat enable

# Disable heartbeat
suzent heartbeat disable

# Set the heartbeat interval (in minutes)
suzent heartbeat interval 15

# Trigger an immediate heartbeat tick
suzent heartbeat run
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

The `HeartbeatRunner` runs independently:

```
┌──────────────────┐
│  HeartbeatRunner  │  sleep(interval)
│  ._run_loop()     │──────────────────┐
└──────────────────┘                   │
                                       ▼
                              ┌─────────────────┐
                              │ Read HEARTBEAT.md│
                              │ from /shared/    │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ Process turn in  │
                              │ heartbeat-main   │
                              │ (persistent)     │
                              └────────┬────────┘
                                       │
                              ┌────────▼────────┐
                              │ HEARTBEAT_OK?    │
                              │ Yes → suppress   │
                              │ No → notify      │
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

### Heartbeat Won't Enable

**Problem:** "HEARTBEAT.md not found" error

**Solutions:**
1. Create `/shared/HEARTBEAT.md` via the Settings editor or file tools
2. Copy the template: `config/HEARTBEAT.example.md`
3. Ensure the file has meaningful content (not just headers)

### HEARTBEAT_OK Not Suppressing

**Problem:** Getting notifications even when agent says HEARTBEAT_OK

**Solutions:**
1. Ensure the agent's response contains exactly `HEARTBEAT_OK` (case-sensitive)
2. Extra text around the sentinel must be under 300 characters
3. Check that the response isn't wrapped in markdown formatting
