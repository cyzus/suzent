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
| Encrypted API key bundles (optional, see [Mnemonic](./shibboleth.md)) | `sync_secret.key` (legacy; never pushed) |

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
        bundles.json          # only if encrypted API sync enabled
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
| **Mnemonic phrase** | Optional | Only if you enable encrypted API key sync |

No CLI tools, personal access tokens, or external apps required. Authentication uses **GitHub's Device Flow** — you authorise Suzent directly in your browser.

## Quick start (Settings → Data)

1. Open **Settings → Data** and find **GitHub Sync**.
2. Click **Connect GitHub** and complete the browser authorisation flow. Suzent shows a code; paste it at github.com/login/device.
3. Optionally change the repository name (default: `suzent-brain`). This creates or links `your-github-username/suzent-brain`.
4. Click **Quick start**.

Quick start will:

- Use the authorised GitHub token to create or clone the sync repository.
- Create `~/.suzent/github-sync` and initialise Git if needed.
- Add remote `origin` pointing at your GitHub repo.
- Create the private GitHub repository if it does not exist and push an initial commit.
- Save a sync profile for automation settings.

### GitHub authentication

Suzent uses **GitHub's Device Flow** (OAuth 2.0). No personal access token or GitHub CLI is needed:

1. Click **Connect GitHub** in the GitHub Sync card.
2. Suzent shows a short user code (e.g. `ABCD-1234`) and opens `github.com/login/device`.
3. Enter the code on GitHub and approve access.
4. Suzent stores the token in the OS keyring and shows your GitHub username.

To sign out, click the username badge and choose **Sign out**.

If the stored token has **expired**, a banner appears prompting you to re-authenticate. Complete the Device Flow again — Quick start and push/pull will resume working immediately.

## Manual workflow

### First machine

1. Complete **Quick start**.
2. Optionally enable **encrypted API sync** and set up a mnemonic phrase (see [Mnemonic](./shibboleth.md)).
3. Click **Push** to publish the current portable brain to GitHub.

### Second machine

1. Install Suzent and complete **Connect GitHub** (Device Flow) on that machine.
2. **Quick start** with the **same repository name**. If the GitHub repo already exists and the local sync folder is empty, Suzent clones the existing repo instead of creating a new separate history.
3. Click **Pull** — config, skills, and memory are restored locally.
4. If encrypted API bundles exist in the repo, Suzent automatically prompts for your mnemonic phrase before importing keys.

### Day-to-day

| Action | When to use |
|--------|-------------|
| **Sync** | Pull remote changes then push local changes in one step |
| **Push** | After changing config, skills, or memory on this device |
| **Pull** | To receive another device's changes; overwrites local portable data |

Pull replaces local portable config, skills, and markdown memory. It preserves device-local files such as `config/sync_profiles.json`. A backup is not created for GitHub pull (unlike folder import); confirm before pulling.

Config and skills are hot-reloaded immediately after a successful pull — no restart needed.

## Advanced options

Open **Advanced options** on the GitHub Sync card to view (read-only) the current profile settings:

| Setting | Default | Purpose |
|---------|---------|---------|
| Local Git repo folder | `~/.suzent/github-sync` | Where the Git repository lives |
| Branch | `main` | Branch to push and pull |
| Remote | `origin` | Git remote name |

Auto-sync settings are in the same card:

| Setting | Default | Purpose |
|---------|---------|---------|
| Auto-sync | On | Periodic pull/push |
| Agent conflict resolve | On | Use agent to help resolve sync conflicts |
| Interval | 4 hours | Auto-sync interval when enabled |

Auto-sync settings save automatically when you toggle them — no save button needed.

## Auto-sync

When **Auto-sync** is enabled, Suzent periodically pulls then pushes for the configured profile.

- Requires a valid GitHub authorisation and clean sync payload rules.
- If **encrypted API sync** is on but the mnemonic is **not unlocked**, auto-sync still moves config/skills/memory but skips importing or exporting API key bundles (a warning is logged).
- The mnemonic is persisted in the OS keyring and auto-loaded between restarts, so auto-sync with secrets works across reboots without manual unlock.

## Diverged branches

If the local and remote branches diverge (e.g. two devices pushed while offline), Suzent automatically rebases:

- **Push**: if the push is rejected as non-fast-forward, Suzent fetches and rebases the local sync commit on top of the remote tip, then pushes again.
- **Pull**: if a fast-forward pull is not possible, Suzent fetches and rebases the local branch onto the remote tip.

In both cases local non-sync changes (anything outside `suzent-sync/`) are preserved by the rebase. If the rebase itself conflicts (rare, e.g. both devices modified the same config key), Suzent hard-resets to the remote state to ensure the remote wins.

## Conflicts

If concurrent edits conflict beyond what automatic rebase handles, push/pull may fail validation. With **Agent conflict resolve** enabled, Suzent can propose resolutions; you can also fix the repo manually with Git and retry.

## API reference

All routes are on the Suzent HTTP API (default `http://127.0.0.1:25314`).

### Authentication

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sync/auth/start` | POST | Start GitHub Device Flow; returns `user_code`, `verification_uri`, `expires_in`, `interval` |
| `/sync/auth/poll` | POST | Poll for Device Flow completion; body: `session_id`. Returns `status` (`pending`/`complete`/`expired`/`denied`) |
| `/sync/auth/status` | GET | Current auth state: `authenticated`, `username`, `token_expired` |
| `/sync/auth/logout` | POST | Clear stored GitHub token |

### Sync operations

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sync/status` | GET | Profile status, mnemonic flags, last revision |
| `/sync/quickstart/info` | GET | Default paths and `github_authenticated` flag |
| `/sync/quickstart` | POST | Run Quick start |
| `/sync/profiles` | GET, POST | List or create profiles |
| `/sync/ahead-behind` | GET | Commits ahead/behind remote |
| `/sync/pull` | POST | Pull and restore payload; optional `shibboleth` (mnemonic phrase) |
| `/sync/push` | POST | Build payload, commit, push; optional `shibboleth` (mnemonic phrase) |
| `/sync/auto/run` | POST | Run one auto-sync cycle (pull + push) |
| `/sync/auto` | POST | Configure auto-sync settings |
| `/sync/shibboleth/unlock` | POST | Cache mnemonic for the session |
| `/sync/shibboleth/lock` | POST | Clear cached mnemonic from memory |
| `/sync/secrets/enable` | POST | Enable encrypted API sync + unlock |
| `/sync/secrets/disable` | POST | Disable encrypted API sync + lock |
| `/sync/secrets/unlock` | POST | Verify and register mnemonic on this device |
| `/sync/secrets/rotate` | POST | Rotate to a new mnemonic; re-encrypts all bundles |
| `/sync/secrets/register-device` | POST | Register this device with an existing mnemonic |

### Related: folder sync (not GitHub)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/data/sync/push` | POST | Write snapshot to a folder path |
| `/data/sync/pull` | POST | Import newest snapshot from a folder |

## Troubleshooting

### GitHub token expired banner

Your previously authorised token has been revoked or expired on GitHub. Click **Connect GitHub** again to complete a new Device Flow. The banner clears automatically once you sign in.

### Quick start shows a pytest or Temp path

An old test profile may have pointed at a temporary directory. Run Quick start again — ephemeral paths under `pytest-of` are ignored and reset to `~/.suzent/github-sync`.

### Fresh device gets "diverging branches" on pull

Suzent now auto-rebases on diverged branches. If it still fails, remove the local sync folder and re-run Quick start — fresh devices clone the existing GitHub repo rather than creating a new unrelated history.

### Push/pull asks for mnemonic

Encrypted API bundles exist in the repo. **Enter your mnemonic** when prompted, or disable encrypted API sync if you only need config/skills/memory on this device.

### Auto-sync skips secrets after restart

If the mnemonic was not persisted to the OS keyring (older setup), unlock once in Settings → Data → GitHub Sync → API Key Sync. Suzent saves it to the keyring and subsequent auto-syncs will load it automatically.

## Common Q&A

### Does GitHub Sync copy my API keys by default?

No. Plaintext API keys, `.env` files, `secrets.db`, and `.secret_key` are excluded. API keys are only written to GitHub as ciphertext in `suzent-sync/_sync/secrets/bundles.json` after you enable encrypted API sync and provide a mnemonic.

### Why is my provider key shown as ENV but not exported?

Environment-only keys can be used by Suzent at runtime, but they are not owned by Suzent's secret store and are not listed for encrypted export. To sync a key, save it through Suzent's provider settings, then push with the mnemonic unlocked.

### Can I pull normal config and memory without a mnemonic?

Yes, if the repo has no encrypted API key bundles. If bundles exist, Suzent asks for the mnemonic so secret import is explicit and never silently skipped.

### Does each device use the same local Git path?

No. `sync_profiles.json` is local to each device. The shared repo content lives under `suzent-sync/`; local repo paths and unlock state stay on each machine.

### Do I still need `gh` CLI or a personal access token?

No. This version replaces both with GitHub's Device Flow. If you have an existing PAT in `GITHUB_TOKEN`, it will still be used for push/pull operations, but new setups no longer need one.

## See also

- [Mnemonic (Encrypted API Sync)](./shibboleth.md) — BIP39 mnemonic, crypto details, multi-device setup
- [Memory](../memory/README.md) — what markdown memory contains
- [Skills](../skills/skills.md) — user skills layout
- [Filesystem & Sandbox](../filesystem.md) — data directory layout
