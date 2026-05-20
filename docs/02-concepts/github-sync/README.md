# GitHub Sync

GitHub Sync keeps a **portable copy** of your Suzent brain in a private Git repository on GitHub. You work locally; Suzent builds a sync payload, commits it, and pushes to your remote. Another machine can pull the same payload and restore config, skills, and markdown memory.

This is separate from the **sync folder** feature on the same Settings → Data page, which writes timestamped ZIP-style snapshots to iCloud, OneDrive, Dropbox, or a NAS path. Use GitHub Sync when you want version history, a GitHub remote, and multi-device sync through Git.

## What syncs vs what stays local

| Included in GitHub sync (`suzent-sync/`) | Stays on this device only |
|------------------------------------------|---------------------------|
| User config (`config/`, excluding device-local sync profiles) | Chat history (`chats.db`) |
| User skills (`skills/`) | LanceDB / search indexes |
| Markdown memory (`memory/`) | Runtime state, caches, sessions |
| Sync manifest and device presence | Plaintext secrets, `.env`, and `sync_profiles.json` |
| Encrypted API key bundles (optional) | `sync_secret.key` (legacy; never pushed) |

Forbidden paths are rejected before push so databases and plaintext secrets cannot enter the repo by mistake.

## Architecture

```
┌─────────────────┐     build payload      ┌──────────────────┐
│  Local Suzent   │ ─────────────────────► │  Local Git repo  │
│  (~/.suzent)    │                        │  github-sync/    │
└─────────────────┘                        └────────┬─────────┘
                                                      │ git push
                                                      ▼
                                             ┌──────────────────┐
                                             │  GitHub private  │
                                             │  user/suzent-    │
                                             │  brain           │
                                             └──────────────────┘
```

Default local repo path: `~/.suzent/github-sync` (under your Suzent data directory).

Inside the repo, portable data lives under `suzent-sync/`:

```
github-sync/
  README.md
  suzent-sync/
    _sync/
      manifest.json
      presence/
        <device-id>.json
      secrets/
        bundles.json          # only if Shibboleth enabled
    config/
    skills/
    memory/
```

Profiles are stored in `~/.suzent/config/sync_profiles.json`. This file is device-local control state and is not synced; each device keeps its own repo path, branch, remote, and unlock state.

## Requirements

| Component | Required? | Notes |
|-----------|-------------|--------|
| **Git** | Yes | On `PATH` for init, commit, push, pull |
| **GitHub account** | Yes | Private repo recommended |
| **GitHub CLI (`gh`)** | Optional | Browser sign-in and `gh repo create` when available |
| **Personal access token** | Optional | Alternative to `gh`; `repo` scope. Paste in Advanced or set `GITHUB_TOKEN` |
| **Shibboleth passphrase** | Optional | Only if you enable encrypted API key sync |

`gh` is a **system tool**, not a Python package — it is not installed via `pip`/`uv`. Install from [cli.github.com](https://cli.github.com/) if you want browser-based sign-in.

## Quick start (Settings → Data)

1. Open **Settings → Data** and find **GitHub Sync**.
2. Optionally change the repository name (default: `suzent-brain`). This creates or links `your-github-username/suzent-brain`.
3. Click **Quick start**.

Quick start will:

- Sign in to GitHub (via `gh` browser flow, or a token you provided).
- Create `~/.suzent/github-sync` and initialize Git if needed.
- Add remote `origin` pointing at your GitHub repo.
- Create the private GitHub repository if it does not exist (and push an initial commit).
- Save a sync profile for automation settings.

### Authentication options

Quick start tries, in order:

1. **Personal access token** — from Advanced options or `GITHUB_TOKEN` in the environment. Stored in the OS keyring for later push/pull.
2. **GitHub CLI** — `gh auth login -w` opens the browser; no token field needed.
3. If neither is available, Quick start fails with instructions to add a token or install `gh`.

Create a classic token with **repo** scope at [github.com/settings/tokens](https://github.com/settings/tokens).

## Manual workflow

### First machine

1. Complete **Quick start** (or configure Advanced: local repo path, branch `main`, remote `origin`).
2. Optionally enable **Shibboleth** and encrypted API sync (see [Shibboleth (Passphrase)](./shibboleth.md)).
3. Click **Push** to publish the current portable brain to GitHub.

### Second machine

1. Install Suzent and sign in to GitHub (`gh` or token) on that machine.
2. **Quick start** with the **same repository name**. If the GitHub repo already exists and the local sync folder is empty, Suzent clones the existing repo instead of creating a new unrelated Git history.
3. Click **Pull** and confirm - config, skills, and memory are restored locally.
4. If encrypted API bundles exist: **Unlock** Shibboleth with the **same passphrase**, then pull. Suzent requires the passphrase before importing API keys.

### Day-to-day

| Action | When to use |
|--------|-------------|
| **Push** | After changing config, skills, or memory on this device |
| **Pull** | Before working on another device’s changes; overwrites local portable data |
| **Validate** | Check repo path, branch, and remote without syncing |
| **Save profile** | Persist Advanced settings (path, branch, remote) |

Pull replaces local portable config, skills, and markdown memory. It preserves device-local files such as `config/sync_profiles.json`. A backup is not created for GitHub pull (unlike folder import); confirm before pulling.

## Advanced options

Open **Advanced options** on the GitHub Sync card:

| Setting | Default | Purpose |
|---------|---------|---------|
| Local Git repo folder | `~/.suzent/github-sync` | Where the Git repository lives |
| Branch | `main` | Branch to push and pull |
| Remote | `origin` | Git remote name |
| Auto-sync | Off | Periodic pull/push (see below) |
| Agent conflict resolve | On | Use agent to help resolve sync conflicts |
| Interval | 4 hours | Auto-sync interval when enabled |
| GitHub personal access token | — | Used when `gh` is not installed or not on the server’s `PATH` |
| Shibboleth | — | Encrypted API key sync (see linked doc) |

Quick start only sends a custom local path if Advanced is open. Otherwise the default `github-sync` folder is used.

## Auto-sync

When **Auto-sync** is enabled, Suzent periodically pulls then pushes for the configured profile.

- Requires a valid Git remote and clean sync payload rules.
- If **encrypted API sync** is on but Shibboleth is **locked**, auto-sync still moves config/skills/memory but **skips** importing or exporting API key bundles (a warning is logged).
- Unlock Shibboleth before a scheduled sync if you need keys to stay in sync.

Save auto-sync settings with **Save auto** after toggling options.

## Conflicts

If the Git repo has changes outside `suzent-sync/` or concurrent edits conflict, push/pull may fail validation. With **Agent conflict resolve** enabled, Suzent can propose resolutions; you can also fix the repo manually with Git and retry.

## API reference

All routes are on the Suzent HTTP API (default `http://127.0.0.1:25314`).

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sync/status` | GET | Profile status, Shibboleth flags, last revision |
| `/sync/quickstart/info` | GET | Default paths, `gh_available`, token configured |
| `/sync/quickstart` | POST | Run Quick start |
| `/sync/profiles` | GET, POST | List or create profiles |
| `/sync/validate` | POST | Validate repo/branch/remote |
| `/sync/preview-pull` | POST | Preview remote vs local hashes |
| `/sync/pull` | POST | Pull and restore payload; optional `shibboleth` |
| `/sync/push` | POST | Build payload, commit, push; optional `shibboleth` |
| `/sync/auto` | POST | Run or configure auto-sync |
| `/sync/shibboleth/unlock` | POST | Unlock session with passphrase |
| `/sync/shibboleth/lock` | POST | Clear unlocked passphrase from memory |
| `/sync/secrets/enable` | POST | Enable encrypted API sync + unlock |
| `/sync/secrets/disable` | POST | Disable encrypted API sync + lock |

### Related: folder sync (not GitHub)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/data/sync/push` | POST | Write snapshot to a folder path |
| `/data/sync/pull` | POST | Import newest snapshot from a folder |

## Troubleshooting

### “No gh detected” but `gh` works in Terminal

The desktop app’s backend may have a narrower `PATH` than your shell. Use a **personal access token** in Advanced, set `GITHUB_TOKEN`, or restart the backend after installing `gh`. Suzent also checks `C:\Program Files\GitHub CLI\gh.exe` on Windows.

### Quick start shows a pytest or Temp path

An old test profile may have pointed at a temporary directory. Run Quick start again after updating — ephemeral paths under `pytest-of` are ignored and reset to `~/.suzent/github-sync`.

### "Unable to add remote origin"

Usually means `origin` already exists while `gh repo create` tried to add it again. Update Suzent and retry Quick start; the repo may already be linked.

### Fresh device gets "fetch first" or "diverging branches"

Update Suzent and retry Quick start. Fresh devices clone an existing GitHub sync repo into an empty local sync folder instead of creating a separate initial commit. If you already created a broken temporary test folder, remove that local folder and run Quick start again.

### Pull fails with another device's local path

Older sync payloads may include `config/sync_profiles.json`, which stores device-local repo paths. Update Suzent and pull again: restore preserves the local sync profile and new pushes exclude it from the payload.

### Push/pull asks for Shibboleth

Encrypted API bundles exist in the repo or encrypted API sync is enabled locally. **Unlock** in Advanced with your passphrase before pull/push, or disable encrypted API sync if you only need config/skills/memory.

## Common Q&A

### Does GitHub Sync copy my API keys by default?

No. Plaintext API keys, `.env` files, `secrets.db`, and `.secret_key` are excluded. API keys are only written to GitHub as ciphertext in `suzent-sync/_sync/secrets/bundles.json` after you enable Shibboleth.

### Why is my provider key shown as ENV but not exported?

Environment-only keys can be used by Suzent at runtime, but they are not owned by Suzent's secret store and are not listed for encrypted export. To sync a key, save it through Suzent's provider settings, then push with Shibboleth unlocked.

### Can I pull normal config and memory without Shibboleth?

Yes, if the repo has no encrypted API key bundles. If bundles exist, Suzent asks for Shibboleth so it does not silently skip or mishandle secret import.

### Does each device use the same local Git path?

No. `sync_profiles.json` is local to each device. The shared repo content lives under `suzent-sync/`; local repo paths and unlock state stay on each machine.

### Backend missing sync routes (404 on `/sync/quickstart/info`)

Restart the Suzent server so it loads the build that includes GitHub Sync routes.

## See also

- [Shibboleth (Passphrase)](./shibboleth.md) — encrypted API key sync, crypto details, multi-device setup
- [Memory](../memory/README.md) — what markdown memory contains
- [Skills](../skills/skills.md) — user skills layout
- [Filesystem & Sandbox](../filesystem.md) — data directory layout
