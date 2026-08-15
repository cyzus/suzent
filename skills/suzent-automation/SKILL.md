---
name: suzent-automation
description: Create, inspect, update, trigger, or troubleshoot Suzent cron jobs and per-chat heartbeat checks. Use for scheduled tasks, recurring reports, reminders, periodic monitoring, and heartbeat configuration.
---

# Automation

Choose the automation type before changing anything:

- Use **cron** for a named task on a precise schedule.
- Use **heartbeat** for periodic monitoring in an existing chat, where several checks can be batched together.

Do not create or modify automation when the user is only asking how scheduling works.

## Runtime semantics

Cron runs in a dedicated persistent chat named `cron-{id}`. It is isolated from the
foreground conversation, but later runs can see that cron chat's prior agent state.
Write each cron prompt so it is still understandable without relying on that history.

Heartbeat runs in the target chat and can see its conversation context. Its checklist
lives in that chat's `heartbeat.md`. If no action is needed, return exactly
`HEARTBEAT_OK`; Suzent suppresses that response and rolls the heartbeat messages back.

Both runners currently enable memory context. Do not assume a memory-search tool is
equipped, and do not write automation prompts that depend on unspecified memories.

## Cron

Use the `suzent cron` CLI through `RunCommandTool` in host mode:

```text
suzent cron list --verbose
suzent cron add --name "daily-summary" --cron "0 9 * * *" --prompt "Summarize today's agenda"
suzent cron trigger <job_id>
suzent cron toggle <job_id>
suzent cron remove <job_id>
suzent cron status
```

In sandbox mode, use `$SUZENT_BASE_URL` and the local API:

| Action | Method | Path |
|---|---|---|
| List | `GET` | `/cron/jobs` |
| Create | `POST` | `/cron/jobs` |
| Update | `PUT` | `/cron/jobs/{id}` |
| Delete | `DELETE` | `/cron/jobs/{id}` |
| Trigger | `POST` | `/cron/jobs/{id}/trigger` |
| Status | `GET` | `/cron/status` |

Create jobs with `name`, `cron_expr`, and `prompt`. Set `delivery_mode` to
`announce` for a status notification or `none` for silent history-only execution.

Suzent retries failures with exponential backoff up to five times; a further failure
deactivates the job. A concurrent run is deferred and counted as a failure, so avoid
schedules shorter than the task's normal duration.

## Heartbeat

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

Keep `heartbeat.md` short and observable. Describe what to inspect, what qualifies as
actionable, and what evidence to report. Do not tell heartbeat to repeat old alerts or
perform destructive/external actions without the normal permission policy.
