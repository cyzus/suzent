# Background Service

Suzent 0.8 can keep automations, heartbeat checks, social channels, and device
connections available after the desktop window closes. The feature is opt-in:
open **Settings > Service** and enable **Background Service**.

The desktop app and the service use the same backend and user data. When the
service is healthy, the desktop app attaches to it instead of starting a second
Python backend. Closing the window does not stop an attached service.

## Platform integration

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

## CLI

```bash
suzent service install          # install, enable at login, and start
suzent service install --no-start
suzent service status
suzent service status --json
suzent service doctor
suzent service restart
suzent service logs             # print the log path
suzent service uninstall        # preserve all user data
```

`suzent service run` runs the same service runtime in the foreground for
diagnosis. Only one service instance can own the runtime lock.

## Resource behavior

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

## Updates and removal

The desktop and standalone update flows stop an installed service gracefully
before replacing the environment and start it again after either a successful
update or rollback. The desktop uninstaller removes the service definition but
does not delete chats, memory, configuration, or other user data.

If the service does not become ready, run `suzent service doctor` and inspect the
path printed by `suzent service logs`. Disabling the Service setting returns an
open desktop app to its owned child backend.
