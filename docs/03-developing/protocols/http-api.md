---
sidebar_position: 1
title: HTTP API and internals
---

# HTTP API and internals

Everything the desktop app does goes through the local HTTP API, on the same
port as the app (`25314` unless you set `SUZENT_PORT`). This page collects the
routes and architecture notes that used to be spread across the user guides.

## Calling Suzent from Inside the Sandbox

`SUZENT_BASE_URL` is injected automatically so sandboxed code can reach the running host server. This lets agent-written scripts do everything the `suzent` CLI can do, without the CLI being installed.

| Variable | Example value |
|----------|---------------|
| `SUZENT_BASE_URL` | `http://host.docker.internal:25314` |

**CLI → API mapping:**

| CLI command | HTTP equivalent |
|-------------|----------------|
| `suzent cron list` | `GET  $SUZENT_BASE_URL/cron/jobs` |
| `suzent cron add ...` | `POST $SUZENT_BASE_URL/cron/jobs` |
| `suzent cron trigger {id}` | `POST $SUZENT_BASE_URL/cron/jobs/{id}/trigger` |
| `suzent cron remove {id}` | `DELETE $SUZENT_BASE_URL/cron/jobs/{id}` |
| `suzent nodes list` | `GET  $SUZENT_BASE_URL/nodes` |
| `suzent nodes describe {node_id_or_name}` | `GET  $SUZENT_BASE_URL/nodes/{node_id_or_name}` |
| `suzent nodes invoke {node_id_or_name} ...` | `POST $SUZENT_BASE_URL/nodes/{node_id_or_name}/invoke` |
| `suzent agent chat "msg"` | `POST $SUZENT_BASE_URL/chat` (streaming) |
| List chats | `GET  $SUZENT_BASE_URL/chats` |
| Memory search | `GET  $SUZENT_BASE_URL/memory/archival?query=...` |

Example — scheduling a cron job from sandboxed Python:

```python
import os, requests

base = os.environ["SUZENT_BASE_URL"]

requests.post(f"{base}/cron/jobs", json={
    "name": "daily-report",
    "cron_expr": "0 9 * * *",
    "prompt": "Summarize today's activity",
    "delivery_mode": "announce",
})
```


## Memory

Everything the Memory panel does is available over HTTP, on the same port as the app
(`25314` unless you set `SUZENT_PORT`), so you can script it or wire it into your own tools.

| Endpoint | Method | What it does |
|---|---|---|
| `/memory/core` | GET | Read the core blocks (`persona`, `user`, `facts`, `context`) |
| `/memory/core` | PUT | Overwrite one core block |
| `/memory/file` | GET | Read `MEMORY.md` |
| `/memory/daily` | GET | List the dates that have a daily log |
| `/memory/daily/{date}` | GET | Read one day's log |
| `/memory/archival` | GET | Search remembered facts |
| `/memory/archival/{id}` | DELETE | Forget one fact (records a tombstone) |
| `/memory/stats` | GET | Counts and index size |
| `/memory/project-contexts` | GET | List per-project context files |
| `/memory/project-contexts/{id}` | PUT | Update a project's context |
| `/memory/reindex` | POST | Rebuild the search index from Markdown |
| `/memory/dream/status` | GET | Consolidation progress and pending work |
| `/memory/consolidate` | POST | Run consolidation now |
| `/memory/lint` | POST | Run the notebook audit now |

Editing a core block through `PUT /memory/core` counts as *you* saying it, which outranks
anything the agent worked out on its own — see
[MEMORY.md is half yours](https://suzent.com/docs/concepts/memory#memorymd-is-half-yours).


## Automation

### Scheduled tasks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/cron/jobs` | List all jobs |
| POST | `/cron/jobs` | Create a job |
| PUT | `/cron/jobs/{job_id}` | Update a job |
| DELETE | `/cron/jobs/{job_id}` | Delete a job |
| POST | `/cron/jobs/{job_id}/trigger` | Trigger immediate run |
| GET | `/cron/status` | Scheduler health and job counts |
| GET | `/cron/notifications` | Drain pending announce notifications |


### Heartbeat

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/heartbeat/status` | Heartbeat system status |
| POST | `/heartbeat/enable` | Enable heartbeat |
| POST | `/heartbeat/disable` | Disable heartbeat |
| POST | `/heartbeat/trigger` | Trigger immediate tick |
| GET | `/heartbeat/md` | Read HEARTBEAT.md content |
| PUT | `/heartbeat/md` | Update HEARTBEAT.md content |
| PUT | `/heartbeat/interval` | Set interval (`{"interval_minutes": N}`) |


### Scheduler architecture


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

#### Notification Flow

Both systems deliver notifications through a shared mechanism:

1. Cron jobs with `delivery_mode: "announce"` push results to an in-memory deque
2. Heartbeat alerts route through the scheduler's notification deque via a callback
3. Frontend polls `GET /cron/notifications` every 5 seconds
4. Notifications appear in the status bar

### Scheduler lifecycle

#### Server Lifecycle

Both systems start during server initialization (`init_background_services()`) and stop during shutdown:

- **SchedulerBrain** — ticks every 30 seconds, checking for due jobs
- **HeartbeatRunner** — sleeps for the configured interval (default 30 minutes)

#### Model Resolution

Both systems resolve which LLM model to use in this order:

1. Job-level `model_override` (cron only)
2. User preferences model (from settings)
3. System default

#### Memory

Memory is **disabled** for both cron and heartbeat executions to avoid polluting the knowledge base with routine automated output.


## GitHub Sync

All routes are served by the local Suzent HTTP API.

| Endpoint | Method | Description |
|---|---|---|
| `/sync/status` | GET | Profile and repository status |
| `/sync/quickstart/info` | GET | Default paths and GitHub authentication state |
| `/sync/quickstart` | POST | Create or connect the sync repository |
| `/sync/profiles` | GET, POST | List or save profiles |
| `/sync/plan` | POST | Preview file changes without retaining worktree mutations |
| `/sync/diff` | POST | Load one selected file's textual diff |
| `/sync/pull` | POST | Pull and apply portable files |
| `/sync/push` | POST | Build, commit, and push portable files |
| `/sync/discard-outgoing` | POST | Restore all outgoing changes, or selected `paths` |
| `/sync/auto` | POST | Save automation settings |
| `/sync/auto/run` | POST | Run one automatic sync cycle |
| `/sync/auth/start` | POST | Start GitHub Device Flow |
| `/sync/auth/poll` | POST | Poll Device Flow completion |
| `/sync/auth/status` | GET | Read GitHub authentication state |
| `/sync/auth/logout` | POST | Clear the stored GitHub token |


### Sync repository layout


```text
github-sync/
  suzent-sync/
    config/
      config.yaml
      default.yaml
      skills.json
    skills/
    memory/
```

The default repository path is `~/.suzent/github-sync`. Sync profiles live in
`~/.suzent/config/sync_profiles.json` and are not portable because repository
paths and automation settings are device-specific.


## Social channels

### Channel architecture


The system uses a driver-based architecture:
1.  **ChannelManager**: Central hub that manages platform drivers. Uses Dynamic Loading to load drivers specified in `social.json`.
2.  **SocialChannel (Driver)**: Platform-specific implementation (e.g., `TelegramChannel`, `FeishuChannel`). Handles API polling/WebSockets and format conversion.
3.  **UnifiedMessage**: comprehensive internal message format.
4.  **SocialBrain**: Core logic that bridges the social message queue to the AI Agent. Handles:
    -   Security checks.
    -   Attachment processing (downloading to sandbox).
    -   Agent instantiation (`get_or_create_agent`).
    -   Response streaming.

## Background service

### Platform integration

Suzent installs a current-user service and does not require administrator access:

| Platform | Integration | Recovery policy |
|---|---|---|
| Windows | Per-user `HKCU\\...\\Run` entry | Up to three retries with five-second backoff |
| macOS | `LaunchAgent` | Restart after an unexpected exit |
| Linux | `systemd --user` | `Restart=on-failure` |

The service binds only to `127.0.0.1`. A private, per-process control token is
required for the graceful stop endpoint; the token is never returned by health
or status APIs. Runtime state is validated against both PID and process creation
time so a recycled PID cannot be mistaken for Suzent.

### Resource behavior

Idle memory depends on enabled providers, memory indexing, channels, and native
libraries. Suzent bounds the data structures it owns rather than claiming a
fixed footprint on every machine:

- pending UI notifications are durable and capped at 1,000 records;
- LanceDB and memory indexing initialize on the first agent turn or Memory API use;
- completed host processes expire after 10 minutes and retained metadata is capped;
- host command output is capped at 16 MiB per background process;
- streaming queues and pending approval records have fixed limits;
- the service samples RSS once per minute and gracefully recycles after five
  consecutive samples above 1,024 MiB.

Set `SUZENT_SERVICE_MAX_RSS_MB` to change the watchdog threshold. Values below
256 MiB are clamped because the full agent runtime may legitimately need more.
`SUZENT_SERVICE_RSS_INTERVAL` changes the sampling interval, with a five-second
minimum. Platform supervision starts a fresh process after watchdog recycling.

