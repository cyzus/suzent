---
sidebar_position: 6
title: Automation
description: Scheduled tasks, webhooks, reminders, heartbeat check-ins, goal mode, and keeping Suzent running in the background.
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
| **When called**, by a webhook | "When GitHub tells you about a new issue, triage it" (see [Webhooks](#webhooks)) |

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

The task's error is shown next to it in **Settings → Automation**. A failed run
is retried up to 5 times with increasing delays. If it still fails, a repeating
task skips that run and tries again at its next scheduled time, so it stays on.
A one-time task is switched off instead. When the model rejects the request
outright (for example an invalid request or an expired API key), Suzent does not
retry and goes straight to the next scheduled time. Fix the cause and the next
run picks it up.

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

## Webhooks

A webhook task runs when another program calls it, instead of on a clock. Use it
to let GitHub, Home Assistant, a CI pipeline, or your own scripts hand work to
Suzent: "a build failed, find out why", "a new issue came in, label it".

1. In **Settings → Automation**, add a task and set **Repeat** to
   **When called (webhook)**. Write the prompt as usual, for example
   "Summarize this GitHub push and tell me if anything looks risky."
2. Save it. Suzent shows the task's **webhook URL**. Copy it now: it is shown
   only once.
3. Paste the URL into the other service's webhook settings, or call it
   yourself:

   ```bash
   curl -X POST http://127.0.0.1:25314/hooks/<token> \
     -H "Content-Type: application/json" \
     -d '{"build": "nightly", "status": "failed"}'
   ```

To give one address to a service that sends many kinds of events and let
Suzent sort them out, use the [Mailbox](./mailbox.md) address instead.

Each call runs the task once. The body of the request (up to 64 KB) is passed to
the agent along with your prompt, so the prompt can say what to do with it.
JSON is shown to the agent formatted, and event headers such as
`X-GitHub-Event` are included so it can tell what kind of event arrived.

**Who can call it.** The URL is the password: anyone who has it can run the
task, so treat it like one. If it leaks, click the link button on the task to
issue a new URL; the old one stops working immediately. Pausing or deleting the
task also stops the URL. The agent is told that the request comes from outside
and must not be obeyed as instructions, but the request still reaches it, so
give webhook tasks prompts that only read and report unless you trust the
sender.

**What the caller gets back.** Suzent answers right away with `202 Accepted`
and runs the task in the background, where its result goes to the task's chat
and notifications like any other task. If the task is still busy with an earlier
call, the new call gets `429 Too Many Requests` and is not queued, so the caller
should retry. Failed webhook runs are not retried automatically, because the
request they were carrying is gone; check the task's history instead.

**Reaching it from the internet.** Suzent only listens on your own computer, so
a script on the same machine can call the URL directly. A service on the
internet, such as GitHub, needs a way in.

The easiest is a [relay](#webhooks-through-a-relay) you deploy yourself. You can
also run a tunnel that forwards to Suzent, such as
[Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/)
or [Tailscale Funnel](https://tailscale.com/kb/1223/funnel). Point the tunnel at
`http://127.0.0.1:25314`, add the tunnel's host name to the `SUZENT_ALLOWED_HOSTS`
environment variable (for example `SUZENT_ALLOWED_HOSTS=hooks.example.com`), and
give the service the tunnel address with the same `/hooks/<token>` path. Only
the `/hooks/` path works without signing in through the tunnel; the rest of
Suzent still requires an approved device.

### Webhooks through a relay

A relay is a small server you deploy once, for free on Cloudflare Workers or on
any server with Docker: [suzent-relay](https://github.com/cyzus/suzent-relay).
Suzent connects out to it, so you don't need a tunnel, port forwarding or a
fixed port. There is no Suzent-run relay; you use your own.

1. Deploy suzent-relay by following its README. Note its `https://` address and,
   if you set one, its registration key.
2. In Suzent, open **Settings → Devices → Relay**, enter the address and the key,
   and turn it on. The badge shows **Connected** once Suzent reaches it.
3. Create a webhook task, or choose **Regenerate URL** on an existing one. Suzent
   now shows two URLs: one for this machine and one through the relay. Give the
   relay URL to GitHub or any other service.

Only `/hooks/` addresses can be reached through the relay; the rest of Suzent
can't. The relay can read webhook payloads in transit, so use a relay you
trust. **Reset relay addresses** in the Relay settings issues new relay
addresses, and every relay webhook URL given out before stops working.

Webhooks work only while Suzent is running, and the URL keeps the same address
only when it runs as the [background service](#keep-suzent-running-in-the-background),
which always uses port 25314. Turn the background service on before you hand the
URL to anything. The relay URL stays the same either way, but it also
only works while Suzent is running.

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
Suzent is running.

On Windows and macOS, closing the window can leave Suzent in the notification
area or the menu bar, where it keeps going until you choose **Quit**. Windows
asks each time until you tick **Remember my choice**; macOS minimizes to the
menu bar. Change it under **Settings → Background Service → When you close the
window** (**Ask every time**, **Minimize to tray**, or **Quit Suzent**). On
Linux, closing the window quits.

To keep Suzent running after you quit, and to start it when you sign in, turn
on **Settings → Background Service**. It needs no administrator access, and it
restarts itself if it crashes or uses too much memory. Updates stop and
restart it for you. The desktop app connects to it when you open it.

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
suzent cron add --name "gh-push" --webhook --prompt "Summarize this push"
suzent cron webhook-url <job_id>   # issue a new webhook URL
suzent cron trigger <job_id>   # run now
suzent cron toggle <job_id>    # switch on or off
suzent cron remove <job_id>

suzent heartbeat enable -c <chat_id>
suzent heartbeat interval 15 -c <chat_id>
suzent heartbeat run -c <chat_id>
```

## Troubleshooting

**A task never runs.** Check that it is switched on and that its next run time
is in the future. If you quit Suzent, turn on the background service.

**A task keeps failing.** Read its last error in **Settings → Automation** and
fix the cause; the next scheduled run uses the fix. A one-time task that failed
is switched off, so switch it back on after fixing it.

**A webhook call gets 404.** The URL is wrong, was replaced with a new one, or
the task is switched off. Issue a new URL from **Settings → Automation** if
you no longer have the current one.

**A webhook call from the internet gets 421 or 401.** Add the tunnel's host name
to `SUZENT_ALLOWED_HOSTS` (421), and check that the path starts with `/hooks/`
(401 means the call reached some other part of Suzent).

**A heartbeat seems to do nothing.** That usually means it ran and found
nothing to report, so it removed itself from the chat. Use **Run Now** in the
heartbeat settings to see it work.
