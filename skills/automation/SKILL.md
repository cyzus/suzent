---
name: automation
description: Schedule recurring tasks (cron) and periodic agent check-ins (heartbeat).
---

# Automation Skill

Suzent has two separate automation systems:

## Cron Jobs vs Heartbeat

| | Cron | Heartbeat |
|---|---|---|
| **Purpose** | Execute a specific task at a specific time | Periodic "wake up, check if anything needs attention" |
| **Session** | Isolated (`cron-{id}`) — fresh, stateless | Persistent (`heartbeat-main`) — accumulates context |
| **Timing** | Cron expression (precise) | Fixed interval (default 30 min) |
| **Config** | Per-job prompt | Single `/shared/HEARTBEAT.md` checklist |
| **Batching** | One job = one task | One tick can check multiple things |
| **Context** | No conversation history | Sees recent check history |

**Use Cron when:** The user wants a scheduled action — daily reports, weekly summaries, timed reminders.

**Use Heartbeat when:** The user wants ambient monitoring — "check my inbox", "anything urgent?", "scan for problems". One heartbeat replaces many small cron jobs by batching checks in a single agent turn.

## Cron Jobs

### How It Works

1. User describes what they want automated and how often
2. Help them formulate the **cron expression** and **prompt**
3. Job is created via Settings > Automation or CLI
4. Scheduler fires the prompt in an isolated chat (`cron-{id}`)
5. Results delivered via status bar (announce) or silently logged (none)

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
- `*/5 * * * *` — every 5 minutes
- `0 * * * *` — every hour
- `0 9 * * *` — daily at 9:00 AM
- `0 9 * * 1-5` — weekdays at 9:00 AM
- `0 9,18 * * *` — twice daily at 9 AM and 6 PM

### Cron CLI

```bash
suzent cron list [--verbose]
suzent cron add --name "daily-summary" --cron "0 9 * * *" --prompt "Summarize today's agenda"
suzent cron trigger <job_id>
suzent cron toggle <job_id>
suzent cron remove <job_id>
suzent cron status
```

You should use the Bash tool to run these CLI commands.

## Heartbeat

### How It Works

1. User creates `/shared/HEARTBEAT.md` (via Settings > Automation editor or file tools)
2. HeartbeatRunner fires every 30 minutes in a persistent `heartbeat-main` chat
3. Agent reads the checklist, checks each item
4. If nothing needs attention → reply `HEARTBEAT_OK` (notification suppressed)
5. If something is actionable → surface it via the status bar

### HEARTBEAT.md Format

The checklist lives at `/shared/HEARTBEAT.md` (alongside `/shared/memory/`). Keep it concise:

```markdown
# Heartbeat Checklist

- Quick scan: anything urgent in recent conversations?
- If a task was left incomplete, note what is missing.
- Check for any pending follow-ups.
```

The agent can read and edit this file directly using the file tools (`/shared/HEARTBEAT.md`). Users can also edit it from Settings > Automation in the heartbeat card.

Rules for the agent during heartbeat:
- Follow the checklist strictly
- Do not infer or repeat old tasks from prior heartbeats
- Reply `HEARTBEAT_OK` if nothing needs attention

### Heartbeat CLI

```bash
suzent heartbeat status
suzent heartbeat enable
suzent heartbeat disable
suzent heartbeat run
```

## Important Notes

- Cron jobs are **isolated and stateless** — each run starts fresh
- Heartbeat is **persistent and context-aware** — sees its own recent history
- **Memory is disabled** for both to avoid polluting the knowledge base
- Cron jobs that fail 5 times are **automatically deactivated**
- The cron scheduler ticks every 30 seconds; heartbeat interval is configurable (default 30 min)
- HEARTBEAT.md is stored in `/shared/` so both the agent and the frontend can access it
