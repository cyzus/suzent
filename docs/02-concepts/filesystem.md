---
sidebar_position: 5
title: Workspace & sandbox
description: Which folders your agent can reach, where its files go, how to run code in an isolated sandbox, and how to undo a turn.
---

# Workspace & sandbox

**Sovereign vessel.** A sovereign agent runs in a space you control. The
settings on this page decide exactly which folders it can reach and where its
code runs, granted deliberately by you, not inherited from a platform. See
[what makes an agent sovereign](https://suzent.com/sovereign).

## Two ways to run

| | Host mode (default) | Sandbox mode |
|---|---|---|
| **Where commands run** | Directly on your computer | Inside an isolated Docker container |
| **What it can reach** | Its workspace folders and folders you mount, nothing else | Only the folders mounted into the container |
| **Needs** | Nothing extra | Docker Desktop (Windows, macOS) or Docker Engine (Linux) |

Turn the sandbox on for a conversation in its chat settings, or for every
conversation in **Settings → Security**.

## Where files go

Each conversation has its own private folder, plus a folder shared by all
conversations. The agent sees them under the same names in both modes:

| Path | What it is |
|---|---|
| `/persistence` | This conversation's own folder. Relative paths land here, so `report.md` means `/persistence/report.md`. |
| `/persistence/uploads` | Files you attach in the chat or send from a [chat app](./social-messaging.md). |
| `/shared` | Shared by all conversations. Memory lives here. |
| `/mnt/...` | Folders from your computer that you've mounted (see below). |

On disk, these live under `.suzent/sandbox/` in your Suzent folder:
`sessions/<chat-id>/` for each conversation and `shared/` for the shared folder.

The agent cannot read outside these folders. Paths such as `/etc/passwd`,
`../../secret`, or Suzent's own source code are refused.

## Giving the agent access to your folders

To let the agent work on a folder from your computer, mount it. Add a line per
folder to `~/.suzent/config/default.yaml`, in the form
`"folder on your computer:path the agent sees"`:

```yaml
sandbox_volumes:
  - "D:/datasets:/data"
  - "C:/Users/you/Documents/MyVault:/mnt/notebook"
```

Now the agent sees `D:/datasets/file.csv` as `/data/file.csv`. In host mode,
shell commands can reach mounted folders through `$MOUNT_<NAME>` variables, and
`$PROJECT_PATH` and `$SHARED_PATH` point at the conversation and shared folders.

## Using the sandbox

1. Install Docker and make sure it is running.
2. Turn the sandbox on (see above).

That's it. Each conversation gets its own container the first time it runs a
command. The container is restarted automatically if it crashes and stopped
after 30 minutes of inactivity. Your files are kept on your computer, so they
survive the container being stopped or removed.

By default the container has Python and the shell, can use the internet, and
is limited to 512 MB of memory and one CPU. Common changes, in
`~/.suzent/config/default.yaml`:

```yaml
sandbox_network: none          # cut the sandbox off from the internet
sandbox_image: suzent-sandbox  # Python + Node.js + common data packages
```

To use the `suzent-sandbox` image, build it once from your Suzent folder with
`docker compose -f docker/sandbox-compose.yml build`.

<details>
<summary>All sandbox settings</summary>

| Setting | Default | What it does |
|---|---|---|
| `sandbox_enabled` | `false` | Use the sandbox for every conversation |
| `sandbox_image` | `python:3.11-slim` | Docker image to run |
| `sandbox_network` | `bridge` | `bridge` allows internet access, `none` blocks it |
| `sandbox_idle_timeout_minutes` | `30` | Stop idle containers after this long |
| `sandbox_setup_command` | `""` | Command run once when a container is created, such as installing packages |
| `sandbox_env` | `{}` | Extra environment variables (secrets are blocked) |
| `sandbox_volumes` | `[]` | Folders to mount, as `host:container` |
| `shell_denied_env_patterns` | `[]` | Environment variables hidden from host-mode commands, such as `OPENAI_*` |

</details>

## Undoing the last turn (Retry)

Not happy with an answer? Click the retry icon (↺) under the agent's last
reply, or send `/retry` in a chat app. Suzent rolls back everything that turn
did and runs your message again:

- the conversation itself,
- files in the conversation's folder,
- files in folders you mounted.

Two limits to know:

- **Only the last turn** can be retried. There is no multi-step undo.
- **`/shared` is not rolled back**, because other conversations use it too.
  Keep your own backups (or Git) for anything important there.

Suzent snapshots mounted folders before every turn, so very large mounts make
each turn slower. Mount only the folders the agent actually needs.

## Troubleshooting

| Problem | What to check |
|---|---|
| The agent can't find a file | Look in `.suzent/sandbox/sessions/<chat-id>/` on your computer. |
| "Path traversal" error | The path is outside the allowed folders. Mount the folder first. |
| A mounted folder is missing | Check the `sandbox_volumes` line and restart Suzent. |
| The sandbox won't start | Make sure Docker is running (`docker ps`). |
| `node` not found in the sandbox | Build and use the `suzent-sandbox` image (see above). |
| No internet in the sandbox | Set `sandbox_network: bridge` (the default). |
