---
sidebar_position: 3
title: Configuration files
description: Where Suzent keeps your data and settings, the settings you can edit by hand, and the environment variables it reads.
---

# Configuration files

Almost everything can be changed in **Settings**, and that is the easiest way.
This page is for the settings that have no screen yet, and for knowing where
your files are. Your memory, skills, and settings are plain files you can read,
edit, and back up.

## The data folder

Suzent keeps your data in a `.suzent` folder in your home folder: `~/.suzent`
on macOS and Linux, `C:\Users\<you>\.suzent` on Windows. To keep it somewhere
else, set the `SUZENT_DATA_DIR` environment variable before starting Suzent.

| Path | What it holds |
|---|---|
| `config/` | Your settings files (see below). |
| `chats.db` | Your conversations. |
| `sandbox/projects/<project>/` | Each [project's workspace](../03-features/filesystem.md#where-files-go). |
| `sandbox/shared/` | The folder shared by all projects. Your memory's Markdown files are in `sandbox/shared/memory/`. |
| `notebook/` | The [notebook](../03-features/memory/llm-wiki.md) vault. |
| `memory/` | The memory search index, rebuilt from the Markdown files. |
| `skills/` | Skills you added. See [Skills](../03-features/skills.md). |
| `transcripts/` | A transcript of each conversation. |
| `runtime/` | Logs. `server.log` is the background service's log. |
| `github-sync/` | The local copy used by [GitHub Sync](../03-features/github-sync.md). |
| `browser_profile/` | The agent's own browser profile, when it remembers logins. |

API keys are not kept in these files. Suzent stores them in your system's
keychain, or in an encrypted `secrets.db` in this folder when no keychain is
available.

## The Suzent folder

A few files live in the folder Suzent is installed in (`~/suzent` if you
installed with the terminal script), not in the data folder:

| File | What it holds | In the app |
|---|---|---|
| `.env` | Environment variables read when the server starts, such as `SEARXNG_BASE_URL`. | |
| `config/social.json` | Chat app connections and allowed users. `config/social.example.json` shows every option. | **Settings → Social Channels** |

## Settings files

These are in `~/.suzent/config/`:

| File | What it holds |
|---|---|
| `default.yaml` | Your own settings, for anything without a screen in the app. Synced by GitHub Sync. |
| `local.yaml` | Settings that only make sense on this computer, such as folder paths. Never synced. |
| `config.yaml` | Preferences the app saves for you. Let the app manage it. |
| `permissions.yaml` | Your **Always allow** rules and the default permission mode. See [Permissions & approvals](../03-features/tools/human-in-the-loop.md#where-rules-are-kept). |
| `permission-audit.jsonl` | A log of every permission decision. |
| `skills.json` | Which skills are switched on or off. |

Suzent reads its settings in this order, and a later file wins:

1. `config/default.example.yaml` in the Suzent folder, which ships the defaults.
2. `config/default.yaml` in the Suzent folder, if you made one.
3. `~/.suzent/config/default.yaml`.
4. `~/.suzent/config/local.yaml`.

Keep your changes in `~/.suzent/config/` so updates never touch them. Setting
names are not case-sensitive. Restart Suzent after editing a file.

A list set in a later file replaces the whole list from an earlier one. This
matters for `sandbox_volumes`: choosing a notebook folder in
**Settings → Memory System** writes `sandbox_volumes` to `local.yaml`, and from
then on any `sandbox_volumes` in `default.yaml` is ignored. Keep all your
mounted folders in `local.yaml`.

## Common settings

### Workspace and sandbox

See [Workspace & sandbox](../03-features/filesystem.md).

| Setting | Default | What it does | In the app |
|---|---|---|---|
| `sandbox_enabled` | `false` | Run commands in a Docker sandbox for every conversation. | **Settings → Security** |
| `sandbox_image` | `python:3.11-slim` | The Docker image the sandbox uses. | |
| `sandbox_network` | `bridge` | `bridge` lets the sandbox use the internet, `none` blocks it. | |
| `sandbox_idle_timeout_minutes` | `30` | Stop a sandbox after this many idle minutes. | |
| `sandbox_setup_command` | `""` | A command run once when a sandbox is created, such as installing packages. | |
| `sandbox_env` | `{}` | Extra environment variables inside the sandbox. | |
| `sandbox_volumes` | | Folders from your computer to mount in every conversation, as `"host folder:path the agent sees"`. Put this in `local.yaml`. | **Settings → Memory System** sets the notebook mount |
| `sandbox_data_path` | `~/.suzent/sandbox` | Where project workspaces and the shared folder are kept. Put this in `local.yaml`. | |
| `shell_denied_env_patterns` | `[]` | Environment variables hidden from commands the agent runs in host mode, such as `OPENAI_*`. | |

### Memory

See [Memory](../03-features/memory/README.md). More tuning is on
[Advanced memory settings](../03-features/memory/configuration.md).

| Setting | Default | What it does | In the app |
|---|---|---|---|
| `memory_enabled` | `true` | Turn long-term memory on or off. | **Settings → Memory System** |
| `markdown_memory_enabled` | `true` | Write remembered facts to Markdown files. | |
| `embedding_model` | | The model used for memory search. | **Settings → Model Roles** |
| `extraction_model` | | The model that picks out facts to remember. | **Settings → Model Roles** |
| `notebook_dir` | `~/.suzent/notebook` | Where the notebook vault is kept. | |
| `memory_consolidation_enabled` | `true` | Let Suzent tidy memory into the notebook in the background. | |
| `memory_lint_enabled` | `true` | Let Suzent audit the notebook for contradictions and broken links. | |
| `lancedb_uri` | `~/.suzent/memory` | Where the memory search index is kept. Put this in `local.yaml`. | |

### Conversations

| Setting | Default | What it does |
|---|---|---|
| `max_context_tokens` | `0` | Cap the context budget. `0` uses whatever the model supports. |
| `context_compaction_trigger` | `0.80` | How full the context gets before older messages are summarized. |
| `goals_max_turns` | `20` | How many turns [goal mode](../03-features/automation.md#goal-mode) runs before pausing. |
| `jsonl_transcripts_enabled` | `true` | Keep a transcript of each conversation. |
| `transcript_indexing_enabled` | `false` | Make past conversations searchable, at the cost of extra embedding calls. |
| `session_daily_reset_hour` | `0` | UTC hour at which conversations reset each day. `0` turns it off. |
| `session_idle_timeout_minutes` | `0` | Reset a conversation after this many idle minutes. `0` turns it off. |

### Devices and other agents

See [Devices & other agents](../03-features/nodes.md). The app saves these in
`local.yaml`.

| Setting | Default | What it does | In the app |
|---|---|---|---|
| `node_lan_bind` | `false` | Let other devices on your network reach this computer. Takes effect after a restart. | **Settings → Mesh → Network access** |
| `node_discovery_enabled` | `true` | Announce this computer on your network so other devices can find it. | |
| `a2a_enabled` | `false` | Publish a card so other A2A agents can find this device. | **Settings → Mesh** |
| `a2a_agent_name` | `""` | The name on that card. Blank uses the computer's name. | **Settings → Mesh** |

### Permissions

`default_permission_mode` in `permissions.yaml` sets the mode new
conversations start in: `default` (**Ask**), `auto` (**Smart**), or
`full_access` (**Full Access**). Choosing a mode in a new chat, before its
first message, saves it here.

## Changing settings from the terminal

`suzent config show` prints the settings the running server reports, and
`suzent config set <key> <value>` changes a saved preference such as
`sandbox_enabled` or `memory_enabled`. See
[Command line](./cli.md#configuration).

## Environment variables

Set these in your environment before starting Suzent. `SEARXNG_BASE_URL` can
also go in the `.env` file in the Suzent folder.

| Variable | What it does |
|---|---|
| `SUZENT_DATA_DIR` | Use a different data folder instead of `~/.suzent`. |
| `SUZENT_PORT` | The port Suzent's server uses. Default `25314`. |
| `SEARXNG_BASE_URL` | Use your own [SearXNG](https://docs.searxng.org/) instance for web search instead of DuckDuckGo. |
| `SKILLS_DIR` | Extra folders to load skills from. Separate several with `:` (macOS, Linux) or `;` (Windows). |
| `SUZENT_SECRET_BACKEND` | Set to `encrypted_sqlite` to keep API keys in the encrypted `secrets.db` instead of your system's keychain. |
| `SUZENT_BROWSER_*` | Browser options when running without the desktop app. See [Browser](../03-features/tools/browser.md#running-suzent-from-the-command-line). |

Provider API keys, such as `OPENAI_API_KEY`, can also be set as environment
variables. Each provider's page lists its variable; see
[Models & Providers](../04-models/README.md).
