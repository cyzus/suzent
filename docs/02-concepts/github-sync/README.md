# GitHub Sync

GitHub Sync keeps a portable copy of Suzent configuration, user skills, and
Markdown memory in a private Git repository. Credentials remain on each device.

## What syncs

| Included in `suzent-sync/` | Device-local only |
|---|---|
| `default.yaml`, `config.yaml`, and `skills.json` | API keys and provider credentials |
| User skills | `.env`, `.secret_key`, `secrets.db`, and `local.yaml` |
| Markdown memory | Chat databases, indexes, caches, sessions, and non-Markdown attachments |
| | MCP definitions, permission rules, node identity, and ChatGPT authentication |

The payload builder rejects forbidden paths before push. GitHub sync never
creates encrypted key bundles and never reads from Suzent's local secret store.

## Repository layout

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

## Setup

1. Open **Settings → Data → GitHub Sync**.
2. Sign in through GitHub Device Flow.
3. Choose a private repository name or accept `suzent-brain`.
4. Select **Quick start**.

On another device, sign in to GitHub, use the same repository, and pull the
portable files. Configure API keys separately on that device.

## Operations

| Action | Purpose |
|---|---|
| **Push** | Publish local config, skills, and memory |
| **Pull** | Apply remote portable files locally |
| **Discard outgoing** | Restore one or all outgoing local files from the committed payload |
| **Use cloud** | Apply the remote payload as the local source of truth |

Plans classify changes as incoming or outgoing. Files are collapsed by default;
selecting a file loads only that file's diff, without generating patches for the
rest of the plan.
The toolbar is contextual: **Pull** appears only for incoming files, **Push**
appears only for outgoing files, and neither is shown when the repository is up
to date. Mixed changes are resolved explicitly in the review instead of through
a separate combined Sync action.
Individual outgoing changes can be discarded without affecting the others.
Incoming changes are still applied as a complete cloud payload because a Git
pull advances the repository as a whole.
Protected memory replacement or deletion requires confirmation. Planning hashes
the portable source trees directly without modifying the repository worktree and
is serialized with sync execution.

Git commits and refs are the revision source of truth. Sync does not maintain a
second manifest, device-presence files, revision UUIDs, or Git tags.

Config and skills are reloaded after a successful pull. Device-local excluded
files are preserved.

## Auto-sync

Auto-sync runs at the configured interval. If only remote files changed, it
pulls and applies them. If local files changed, it builds and pushes a portable
payload. Destructive memory changes require review.

## API

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

## Legacy encrypted bundles

Earlier versions could store encrypted API-key bundles under
`suzent-sync/_sync/secrets/`. File-only sync no longer imports, exports, or
preserves `_sync/`. The next payload build removes that legacy directory from
the current branch, but historical ciphertext remains in Git history.

Ensure required keys exist in the local secret store before upgrading another
device. Rotate provider keys if the repository or old recovery phrase may have
been exposed.

## Troubleshooting

### A provider works on one device but not another

Credentials are deliberately device-local. Configure the provider key on the
new device or use a supported external secret provider when one becomes
available.

### The GitHub token expired

Sign in again through GitHub Sync. Suzent stores the GitHub authorization token
in the OS keyring; it is separate from provider API keys.

### A pull reports diverging branches

Retry after fetching or re-run Quick start on a clean local sync directory.
Avoid editing generated payload files directly.

## See also

- [Memory](../memory/README.md)
- [Skills](../skills/skills.md)
- [Filesystem and sandbox](../filesystem.md)
