---
sidebar_position: 6
title: Automation
description: Scheduled tasks, reminders, heartbeat check-ins, goal mode, and keeping Suzent running in the background.
---

# Automation

**Sovereign authority.** Work that happens while you aren't watching is the
sharpest edge of an agent's autonomy. Every scheduled task runs on a schedule
and instructions you wrote, and with a cautious permission mode you can't
accidentally widen (see [When nobody is watching](./tools/human-in-the-loop.md#when-nobody-is-watching)).
See [what makes an agent sovereign](https://suzent.com/sovereign).

Suzent can work on its own schedule: send you a morning summary, check on a
build every 15 minutes, remind you about something next week, or keep working
toward a goal until it's done.

## Scheduled tasks

Create tasks in **Settings → Automation**, with `suzent cron` on the command
line, or simply by asking the agent ("every weekday at 9, summarize my
inbox").

Each task answers two questions.

**When does it run?**

| Schedule | Example |
|---|---|
| **Every N minutes** | "Check the build every 15 minutes" |
| **Hourly, daily, weekly, monthly**, or a cron expression | "Every weekday at 9:00" |
| **Once**, at a set time | "Remind me about the migration on Friday at 10:00" |

**Where does it run?**

| Runs in | Good for |
|---|---|
| **Its own chat** (default) | Self-contained jobs such as a daily report. The task sees only its own past runs, so write the prompt to stand alone. This keeps each run cheap. |
| **An existing conversation** | Following up on something you were just discussing, like "has CI finished on that PR?" The task sees the whole conversation, which costs more tokens as the chat grows. |

A task in an existing conversation can be set to **quiet**: if it has nothing
to report, it leaves the conversation untouched. When it does find something,
the answer appears in the chat under a "Scheduled Task" header.

You can also choose:

- **Notifications:** show the result in the app's status bar (**announce**), or
  just keep it in the task's history (**none**).
- **Time zone**, so "9:00" stays 9:00 wherever your computer is.
- **Jitter**, a small random delay so many tasks don't fire at the same second.
- **Catch-up:** what to do about runs missed while your computer was asleep.
  By default they're skipped; choose "run once" to make up a single run.
  One-time reminders always run, however late.

### Tasks the agent schedules for itself

The agent can set its own follow-ups ("The deploy is running. I'll check back
in 15 minutes."). To keep this under control, it can have at most 5 such tasks
per chat, can't repeat more often than every 5 minutes, and can only change or
cancel tasks it created. Tasks you set up are yours.

### When a task fails

The task's error is shown next to it in **Settings → Automation**. Failed runs
are retried with increasing delays, and after 5 failures in a row the task is
switched off. Fix the cause (often an expired API key), then switch it back on.

### Cron expressions

For custom schedules, a cron expression has five fields: minute, hour, day of
month, month, day of week (0 is Sunday).

| Expression | Runs |
|---|---|
| `*/5 * * * *` | Every 5 minutes |
| `0 * * * *` | Every hour |
| `0 9 * * *` | Every day at 9:00 |
| `0 9 * * 1-5` | Weekdays at 9:00 |
| `0 9,18 * * *` | At 9:00 and 18:00 |
| `0 0 * * 0` | Sundays at midnight |
| `0 0 1 * *` | The first of every month |

## Heartbeat

A heartbeat is a regular check-in inside one conversation, driven by a
checklist you write. Use it for "keep an eye on this" work.

1. Open the conversation and its **Config** tab in the left sidebar.
2. Turn on **Heartbeat** and set how often it runs (every 30 minutes by
   default).
3. Edit its `heartbeat.md` checklist, for example:

   ```markdown
   - Anything urgent in recent conversations?
   - If a task was left unfinished, note what is missing.
   - Any follow-ups due today?
   ```

When nothing needs attention, the agent answers `HEARTBEAT_OK` and the
check-in is removed from the chat, so your history doesn't fill up with
"all clear" messages. When something does need attention, it shows up in the
chat and the status bar.

## Goal mode

Goal mode keeps the agent working toward an objective across many turns,
without you prompting each step. Use it when "done" is easy to check, such as
"Fix every lint error in `src/` and make sure `ruff check` passes."

- Type `/goal <objective>` in the chat. The agent starts right away.
- After each turn, a quick check (using the **Goal Judge** model role, which falls back to
  **Decision**) decides
  whether the goal is met. If not, the agent continues automatically.
- It stops when the goal is achieved, or pauses after 20 turns.
- Anything you type takes priority. Your message runs first, then the goal
  continues.

The **Goal** tab in the right sidebar shows progress and has Pause, Resume,
and Clear buttons. You can also use these commands:

| Command | What it does |
|---|---|
| `/goal <objective>` | Set a goal and start |
| `/goal` | Show the current goal and progress |
| `/goal pause` / `/goal resume` | Pause, or resume with a fresh turn budget |
| `/goal clear` | Remove the goal |
| `/subgoal <text>` | Add a condition that must also be met |
| `/subgoal remove <N>` / `/subgoal clear` | Remove one or all extra conditions |

Change the 20-turn limit with `goals_max_turns` in
`~/.suzent/config/default.yaml`.

## Keep Suzent running in the background

Scheduled tasks, heartbeats, chat apps, and paired devices only work while
Suzent is running. To keep them going after you close the window, turn on
**Settings → Background Service**.

Suzent then starts when you sign in and keeps running without the window. The
desktop app connects to it when you open it, and closing the window doesn't
stop it. It needs no administrator access, and it restarts itself if it
crashes or uses too much memory. Updates stop and restart it for you.

The same thing from the command line:

```bash
suzent service install     # install, start at sign-in, and start now
suzent service status
suzent service doctor      # diagnose a service that won't start
suzent service logs        # show where the log file is
suzent service uninstall   # remove the service (your data is kept)
```

## Command line

Everything in **Settings → Automation** is also available from the terminal:

```bash
suzent cron list
suzent cron add --name "daily-summary" --cron "0 9 * * *" --prompt "Summarize today's agenda"
suzent cron add --name "poll-ci" --every 15 --prompt "Check the build"
suzent cron add --name "follow-up" --at "2026-01-02T09:00" --prompt "Revisit the migration"
suzent cron add --name "report" --cron "0 9 * * *" --timezone Asia/Shanghai --prompt "Morning report"
suzent cron add --name "watch-pr" --every 30 --chat <chat_id> --quiet --prompt "Has CI finished?"
suzent cron trigger <job_id>   # run now
suzent cron toggle <job_id>    # switch on or off
suzent cron remove <job_id>

suzent heartbeat enable -c <chat_id>
suzent heartbeat interval 15 -c <chat_id>
suzent heartbeat run -c <chat_id>
```

## Troubleshooting

**A task never runs.** Check that it is switched on and that its next run time
is in the future. If you closed the app, turn on the background service.

**A task was switched off.** It failed 5 times in a row. Read its last error,
fix the cause, and switch it back on.

**A heartbeat seems to do nothing.** That usually means it ran and found
nothing to report, so it removed itself from the chat. Use **Run Now** in the
heartbeat settings to see it work.
