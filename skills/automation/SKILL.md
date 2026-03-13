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
| **Session** | Isolated (`cron-{id}`) — fresh, stateless | Per-session — executes in the target chat's context |
| **Timing** | Cron expression (precise) | Configurable interval (default 30 min) |
| **Config** | Per-job prompt | Per-session `heartbeat.md` instructions |
| **Batching** | One job = one task | One tick can check multiple things |
| **Context** | No conversation history | Sees recent check history in that chat session |

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

1. User enables heartbeat in the chat's left sidebar settings (Config)
2. HeartbeatRunner fires at a configurable interval (default 30 minutes) within the specific chat session
3. Agent reads the `heartbeat.md` instructions configured for that chat, checks each item
4. If nothing needs attention → reply `HEARTBEAT_OK` (notification suppressed and history rolled back)
5. If something is actionable → surface it via the status bar or the chat

### heartbeat.md Format

The checklist lives in the chat config itself. Keep it concise:

```markdown
# Heartbeat Checklist

- Quick scan: anything urgent in recent conversations?
- If a task was left incomplete, note what is missing.
- Check for any pending follow-ups.
```

The user configures this from the specific chat's sidebar.

Rules for the agent during heartbeat:
- Follow the checklist strictly
- Do not infer or repeat old tasks from prior heartbeats
- Reply `HEARTBEAT_OK` if nothing needs attention

### Heartbeat CLI

```bash
suzent heartbeat status -c <chat_id>
suzent heartbeat enable -c <chat_id>
suzent heartbeat disable -c <chat_id>
suzent heartbeat run -c <chat_id>
suzent heartbeat interval <minutes> -c <chat_id>   # set the check-in interval (e.g. 15)
```

## Important Notes

- Cron jobs are **isolated and stateless** — each run starts fresh
- Heartbeat executes in the **existing persistent chat session** allowing it to see its own recent history
- **Memory is disabled** for both to avoid polluting the knowledge base
- Cron jobs that fail 5 times are **automatically deactivated**
- The cron scheduler ticks every 30 seconds; heartbeat polls every 1 minute and triggers based on the chat's configured interval (default 30 min)
