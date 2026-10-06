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
| **What it can reach** | Its project library, the shared folder, and folders you mount, nothing else | Only the folders mounted into the container |
| **Needs** | Nothing extra | Docker Desktop (Windows, macOS) or Docker Engine (Linux) |

Turn the sandbox on for a conversation in its chat settings, or for every
conversation in **Settings → Security**.

## Where files go

Every [project](#projects) has its own library folder, shared by all of the
project's conversations, plus one folder shared by every project:

| Folder | What it is | Sandbox path | Host-mode path |
|---|---|---|---|
| Project library | The project's files: its context note, notes, deliverables, and uploads. | `/workspace` | `$PROJECT_PATH` |
| Scratch | Throwaway files such as helper scripts and downloads. The agent's working folder unless the chat has its own **Working Dir**. Not part of the library, and trimmed once it passes `scratch_max_mb`. | `/workspace/scratch` | `$PROJECT_PATH/scratch` |
| Uploads | Files you attach in the chat or send from a [chat app](../05-chat-apps/README.md). | `/workspace/uploads` | `$PROJECT_PATH/uploads` |
| Shared | Shared by all projects. Memory lives here. | `/shared` | `$SHARED_PATH` |
| Mounted folders | Folders from your computer that you've mounted (see below). | the path you chose, e.g. `/data` | A variable named after that path, e.g. `$DATA` |

In host mode the agent works with the real folders on your computer, so the
sandbox paths don't exist there; shell commands use the variables instead.
`$PROJECT_PATH` and `$SHARED_PATH` work in the sandbox too, so scripts that use
them run in either mode.

On your computer, these folders live under `~/.suzent/sandbox/`:
`projects/<project>/` for each project's library and `shared/` for the shared
folder.

### What goes in the project library

The library is for things a later chat in the project should be able to find,
not for everything the agent touches along the way. The agent sorts what it
writes like this:

| If it is... | It goes to |
|---|---|
| Useful beyond this project, such as a concept, a paper summary, or a comparison | Your [notebook](./memory/llm-wiki.md), when you've asked it to file there |
| Only meaningful to this project, such as goals, decisions, or a finished report | The project library |
| Only needed for the task at hand, such as a helper script, a download, or intermediate output | The project's `scratch/` folder |

Inside the library, the agent keeps finished work in `artifacts/` and notes worth
keeping in `notes/`. It lists every library file, one line each, in the
project's `context.md`, so the next chat knows what's already there. Generated
images, videos and speech go into `artifacts/` and are listed automatically.

<a id="projects"></a>

Conversations start in the default project. Use **New project** in the sidebar
(or **Move to project** on a chat) to group related conversations, so they share a library and project memory
without seeing another project's files.

The agent cannot read outside these folders. Paths such as `/etc/passwd`,
`../../secret`, or Suzent's own source code are refused.

## Giving the agent access to your folders

To let the agent work on a folder from your computer, mount it.

The quickest way is the **Working Dir** button in the chat box: choose a folder,
or pick one from **Recent folders**, and it's mounted for that conversation.
Click it again to see or remove what's mounted.

To mount a folder for every conversation, add a line per folder to
`~/.suzent/config/local.yaml` (settings in that file stay on this computer), in the form
`"folder on your computer:path the agent sees"`:

```yaml
sandbox_volumes:
  - "D:/datasets:/data"
  - "C:/Users/you/Documents/MyVault:/mnt/notebook"
```

Now the agent sees `D:/datasets/file.csv` as `/data/file.csv`. In host mode,
shell commands reach the same folder through a variable named after the path:
`/data` becomes `$DATA`, and a path under `/mnt/` such as `/mnt/notebook`
becomes `$MOUNT_NOTEBOOK`.

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
- files the agent created or edited with its file tools, wherever they are.

Two limits to know:

- **Only the last turn** can be retried. There is no multi-step undo.
- **Changes made by shell commands are not undone**, such as installed
  packages or files a script wrote. Keep your own backups (or Git) for
  anything important.

## Troubleshooting

| Problem | What to check |
|---|---|
| The agent can't find a file | Look in `~/.suzent/sandbox/projects/<project>/` on your computer. |
| "Path traversal" error | The path is outside the allowed folders. Mount the folder first. |
| A mounted folder is missing | Check the `sandbox_volumes` line and restart Suzent. |
| The sandbox won't start | Make sure Docker is running (`docker ps`). |
| `node` not found in the sandbox | Build and use the `suzent-sandbox` image (see above). |
| No internet in the sandbox | Set `sandbox_network: bridge` (the default). |
