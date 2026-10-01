---
sidebar_position: 1
title: Command line
description: Every suzent command you can run in a terminal, grouped by what it is for, with its most useful options.
---

# Command line

Suzent installs a `suzent` command. Everything the desktop app does can also be
started, checked, or changed from a terminal. Add `--help` to any command to see
all of its options, for example `suzent cron add --help`.

| Option | What it does |
|---|---|
| `--version`, `-V` | Show the installed Suzent version. |
| `--verbose`, `-v` | Print detailed logs while the command runs. |
| `--help` | List commands, or the options of one command. |

Most commands talk to a running Suzent. If one reports that it can't reach the
server, start Suzent first with `suzent start` or the
[background service](../03-features/automation.md#keep-suzent-running-in-the-background).

## Running Suzent

| Command | What it does | Key options |
|---|---|---|
| `suzent start` | Open the desktop app. It runs in the background, so your terminal is free again once it has started. | `--port` |
| `suzent stop` | Stop a Suzent server running on this computer. | `--port` |
| `suzent restart` | Stop Suzent, then start it again. | `--port` |
| `suzent serve` | Run the Suzent server in this terminal without the desktop window. Press Ctrl+C to stop it. | `--host`, `--port` |
| `suzent web` | Open Suzent in your web browser. Uses the background service, and offers to install it if it isn't installed yet. | `--no-open`, `--install` / `--no-install`, `--foreground` |
| `suzent ui` | Open only the desktop window, connecting to a server that is already running. | `--port`, `-p` |
| `suzent logs` | Show the log of a Suzent process started from the terminal. | `--desktop`, `--follow` / `-f`, `--lines` / `-n` (default 200) |
| `suzent doctor` | Check that the tools Suzent needs are installed. | |

The default port is `25314`. Set the `SUZENT_PORT` environment variable to
change it for every command.

`suzent web --foreground` runs a one-off server in the terminal instead of the
background service. Only then do `--port` and `--host` apply. Binding to
anything other than `127.0.0.1` exposes Suzent to your network.

`suzent logs --desktop` shows the desktop app's log. Without an option,
`suzent logs` shows the log of a server started in development mode. The
background service keeps its own log; see `suzent service logs` below.

## Background service

The background service keeps Suzent running after you close the window, so
scheduled tasks and chat apps keep working. The same switch is in
**Settings → Background Service**. See
[Keep Suzent running in the background](../03-features/automation.md#keep-suzent-running-in-the-background).

| Command | What it does | Key options |
|---|---|---|
| `suzent service install` | Install the service, start it at sign-in, and start it now. | `--no-start` to install without starting |
| `suzent service uninstall` | Stop and remove the service. Your data is kept. | |
| `suzent service start` | Start the installed service. | |
| `suzent service stop` | Stop the service. | |
| `suzent service restart` | Restart the service. | |
| `suzent service status` | Show whether it is installed, running, and ready, and how much memory it uses. | `--json` |
| `suzent service doctor` | Diagnose a service that won't start. | |
| `suzent service logs` | Print where the service log file is. | |

## Updating

See [Updating Suzent](../01-getting-started/updating.md) for details.

| Command | What it does | Key options |
|---|---|---|
| `suzent check-update` | Check whether a newer release is available. | `--json`, `--cached` |
| `suzent update` | Update Suzent and the desktop app to the latest release. | `--headless` to update in the terminal without a window |
| `suzent upgrade` | Same as `suzent update`. | `--headless` |
| `suzent repair` | Reinstall the current release, for example after an update was interrupted. | `--headless` |
| `suzent shortcuts` | Create or repair the app's menu entry and shortcuts. | `--desktop` / `--no-desktop`, `--menu` / `--no-menu`, `--remove`, `--json` |

## Chatting from the terminal

| Command | What it does | Key options |
|---|---|---|
| `suzent agent chat [message]` | Chat with your agent in the terminal. It continues your last terminal conversation. | `--new` to start a new conversation |
| `suzent agent current` | Show which conversation the terminal is using. | |
| `suzent agent clear` | Detach the terminal from its conversation. The next chat starts a new one. | |
| `suzent agent status` | Check that the server is running, and show how many tools and connected devices it has. | |
| `suzent agent approve <id>` | Approve a pending tool request. | |
| `suzent agent deny <id>` | Deny a pending tool request. | |

Inside `suzent agent chat`, type `/` to see the
[slash commands](./slash-commands.md) available in the terminal. When the agent
asks for permission, you are asked to allow it right there. Type `exit` or press
Ctrl+C to leave.

## Configuration

| Command | What it does |
|---|---|
| `suzent config show` | Print the settings the running server reports. |
| `suzent config get <key>` | Print one of those settings, for example `suzent config get defaultModel`. |
| `suzent config set <key> <value>` | Change a saved preference, for example `suzent config set sandbox_enabled true`. |

`config set` accepts the preferences the app saves: `model`, `tools`,
`memory_enabled`, `thinking`, `sandbox_enabled`, `sandbox_volumes`,
`embedding_model`, and `extraction_model`. Values such as `true`, `42`, or a
JSON list are converted automatically. For everything else, see
[Configuration files](./configuration.md).

## Skills

| Command | What it does |
|---|---|
| `suzent skill list` | List every skill Suzent found, with where it came from and whether it is on. |
| `suzent skill toggle <name>` | Switch a skill on or off. |
| `suzent skill reload` | Rescan the skill folders after adding or editing skills. |

To install or write a skill, ask the agent. See [Skills](../03-features/skills.md).

## MCP servers

| Command | What it does | Key options |
|---|---|---|
| `suzent mcp list` | List MCP servers and whether each is enabled. | |
| `suzent mcp add <name>` | Add a server, either by URL or by the command that starts it. | `--url` with `--header` / `-H`, or `--command` with `--args` and `--env` / `-e` |
| `suzent mcp test <name>` | Check that a server answers, and list its tools. | |
| `suzent mcp enable <name>` | Enable a server. | |
| `suzent mcp disable <name>` | Disable a server. | |
| `suzent mcp remove <name>` | Remove a server. | |

For example:

```bash
suzent mcp add sqlite --command npx --args "-y,@modelcontextprotocol/server-sqlite,/db"
suzent mcp add docs --url https://example.com/mcp --header "Authorization: Bearer <token>"
```

`--args` takes a comma-separated list. `--header` and `--env` can be repeated.
See [MCP servers](../03-features/tools/tools.md#mcp-servers).

## Scheduled tasks

The same tasks as in **Settings → Automation**. See
[Automation](../03-features/automation.md).

| Command | What it does | Key options |
|---|---|---|
| `suzent cron list` | List your scheduled tasks. | `--verbose` / `-v` |
| `suzent cron add` | Create a task. | See below |
| `suzent cron edit <id>` | Change a task. | `--name`, `--cron`, `--prompt`, `--delivery`, `--model` (`none` clears it) |
| `suzent cron trigger <id>` | Run a task now. | |
| `suzent cron toggle <id>` | Switch a task on or off. | |
| `suzent cron remove <id>` | Delete a task. | |
| `suzent cron history <id>` | Show a task's recent runs. | `--limit` / `-l` (default 10) |
| `suzent cron status` | Show whether the scheduler is running and how many tasks there are. | |
| `suzent cron install-presets` | Add or update the built-in notebook upkeep tasks. | `--activate-existing` |

`suzent cron add` needs a `--name`, a `--prompt`, and exactly one schedule:

| Option | What it does |
|---|---|
| `--cron`, `-c` | Run on a [cron expression](../03-features/automation.md#cron-expressions), such as `"0 9 * * 1-5"`. |
| `--every` | Run every N minutes. |
| `--at` | Run once at a time, such as `"2026-01-02T09:00"`. |
| `--chat` | Run inside an existing conversation instead of the task's own chat. |
| `--quiet` | With `--chat`, leave the conversation untouched when there is nothing to report. |
| `--timezone` | Time zone for a cron schedule, such as `Asia/Shanghai`. |
| `--jitter` | Spread the start time over up to N random seconds. |
| `--catch-up` | After downtime, `skip` missed runs (default) or `run_once` to make one up. |
| `--delivery`, `-d` | `announce` (default) shows the result in the app's status bar; `none` only keeps it in the task's history. |
| `--model`, `-m` | Use a specific model for this task. |
| `--inactive` | Create the task switched off. |

## Heartbeat

A heartbeat is a regular check-in inside one conversation. See
[Heartbeat](../03-features/automation.md#heartbeat).

| Command | What it does |
|---|---|
| `suzent heartbeat status` | Show whether the heartbeat is on. |
| `suzent heartbeat enable` | Turn it on. |
| `suzent heartbeat disable` | Turn it off. |
| `suzent heartbeat run` | Run a check-in now. |
| `suzent heartbeat interval <minutes>` | Change how often it runs. |

Each takes `--chat <id>` (or `-c`) to choose the conversation. Without it, the
conversation your terminal is using is picked.

## Chat app pairing

Handle requests from people asking to use your bot. See
[Access control & pairing](../05-chat-apps/access-control.md).

| Command | What it does |
|---|---|
| `suzent pair list` | List pending requests, with their codes. |
| `suzent pair approve <code>` | Approve a request. |
| `suzent pair deny <code>` | Deny a request. |

## Devices

Pair other computers and phones, and let devices use each other. See
[Devices & other agents](../03-features/nodes.md).

| Command | What it does | Key options |
|---|---|---|
| `suzent nodes discover` | Find Suzent devices on your network and your Tailscale network. | `--timeout` / `-t` (seconds, default 2) |
| `suzent nodes list` | List everything this computer is linked to. | |
| `suzent nodes status` | Show a summary of connected devices. | |
| `suzent nodes describe <device>` | Show what a device can do. | |
| `suzent nodes invoke <device> <command> [key=value ...]` | Run one of a device's commands, such as `speaker.speak text="Hello"`. | `--params` / `-p` (JSON), `--timeout` / `-t` |
| `suzent nodes trigger <peer> <prompt>` | Ask another Suzent's agent to do something, and show its reply. | `--chat-id`, `--file` (repeatable) |
| `suzent nodes pending` | List devices waiting for your approval. | |
| `suzent nodes approve <code>` | Approve a waiting device. | |
| `suzent nodes deny <code>` | Refuse a waiting device. | |
| `suzent nodes devices` | List approved devices. | |
| `suzent nodes revoke <device_id>` | Remove an approved device. It must pair again to reconnect. | |
| `suzent nodes connect <url>` | Join another Suzent as a device, for example from a headless server. | `--name` / `-n` |
| `suzent nodes connections` | List the connections this computer started. | |
| `suzent nodes disconnect <url>` | Stop one of those connections. | |
| `suzent nodes host` | Offer this computer's speaker and camera to Suzent, until you press Ctrl+C. | `--name` / `-n`, `--capabilities` / `-c`, `--url` |

## Editors (ACP)

| Command | What it does | Key options |
|---|---|---|
| `suzent acp` | Let an editor that supports the Agent Client Protocol, such as Zed, use Suzent as its agent. Your editor runs this command; you don't run it yourself. | `--permission-mode` (`default`, `auto`, or `full_access`) |

See [Use Suzent from your editor](../03-features/nodes.md#use-suzent-from-your-editor-acp).

## For developers

`suzent start --dev` and `suzent restart --dev` run Suzent from a source
checkout in development mode, and `suzent update --dev` updates that checkout
to the latest development version. `suzent logs --frontend`
reads the development window's log, and `suzent setup-build-tools` installs
the Windows build tools needed to compile the desktop app. See the
[development guide](../08-developing/contributing/development-guide.md).
