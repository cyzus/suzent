# File-Only GitHub Sync Implementation Plan

Status: **implemented and verified**

## Objective

Limit GitHub sync to portable files and remove encrypted API-key synchronization
from the sync system.

GitHub sync will synchronize:

- portable configuration;
- user skills;
- Markdown memory files.

API keys, credentials, provider tokens, recovery phrases, and secret-manager
sessions will remain device-local. A Bitwarden-compatible secret provider can be
implemented separately without coupling it to file reconciliation.

## Non-goals

- Implementing Vaultwarden or Bitwarden integration in this pull request.
- Synchronizing encrypted credentials through Git.
- Retaining Shibboleth, mnemonic, or shared-key-vault workflows.
- Rewriting Git history to remove historical encrypted bundles.
- Redesigning the complete Git transport layer beyond what safe file
  reconciliation requires.

## Portable-file boundary

The payload may contain only:

```text
config/config.yaml
config/default.yaml
config/skills.json
skills/
memory/**/*.md
```

The payload must exclude:

```text
.env
.secret_key
local.yaml
secrets.db
sync_profiles.json
node_devices.json
node_host_devices.json
node_peers.json
permission-audit.jsonl
permissions.yaml
node_identity.json
mcp_servers.json
chatgpt/**
_sync/secrets/**
```

Database files, runtime data, caches, sessions, exports, backups, device tokens,
and other machine-local state must continue to be excluded.

Configuration uses an allowlist, not an exclusion-only traversal. Pull replaces
only the three portable configuration files and must preserve every other local
configuration file, including files introduced by future features.

Tests must prove that representative API-key values cannot enter the payload
through environment files, local configuration, secret databases, or structured
provider configuration.

## Backend implementation

### Remove secret-sync models

In `src/suzent/sync/models.py`, remove these fields from `SyncProfile`:

```python
encrypted_secret_sync_enabled
secret_sync_available
synced_keys
```

Remove the secret-specific models:

```python
ShibbolethKdfParams
MnemonicKdfParams
DeviceRegistration
EncryptedSecretBundle
SecretBundlesFile
```

Remove their exports from `src/suzent/sync/__init__.py`.

Existing profile JSON may contain obsolete fields. Pydantic should ignore those
fields while loading; saving the profile again should write only the current
schema.

### Delete encryption modules

Delete:

```text
src/suzent/sync/secrets.py
src/suzent/sync/shibboleth.py
src/suzent/sync/mnemonic.py
src/suzent/sync/bip39_english.txt
```

Remove dependencies used exclusively by these modules after verifying that they
have no other consumers.

### Keep planning externally read-only

Push and automatic-sync planning hash portable source trees directly and compare
them with the committed payload. Tests must verify that repository status is
identical before and after planning.

Remove `SECRETS_DIR` and encrypted-bundle preservation. Retain append-only
Markdown memory preservation. Do not copy non-Markdown memory attachments.

Do not generate `_sync/manifest.json` or `_sync/presence/**`. Git commits and
refs already provide revision identity, timestamps, and changed paths. Remove
the random revision UUID, device presence, metadata-only commit filtering, and
the corresponding status UI.

### Simplify the sync service

Remove secret-specific service state and methods, including:

- Shibboleth and mnemonic lock/unlock state;
- mnemonic keyring storage;
- vault enable, disable, rotation, and device registration;
- key selection and vault-key removal;
- secret export, import, overwrite detection, and bundle inspection;
- secret-related fields in status and operation results.

Use simple file-only signatures:

```python
async def pull(
    profile_id: str | None = None,
    *,
    confirm_destructive: bool = False,
    prefer_cloud: bool = False,
) -> dict:
    ...


async def push(
    profile_id: str | None = None,
    *,
    confirm_destructive: bool = False,
) -> dict:
    ...


async def auto_sync(
    profile_id: str | None = None,
    *,
    confirm_destructive: bool = False,
) -> dict:
    ...
```

Operation results must not contain `secrets`, `imported_secret_keys`, or
`changed_secret_keys`.

### Keep planning file-only and read-only

`SyncFileChange.category` should support:

```python
Literal["config", "skills", "memory", "other"]
```

Remove secret categories, vault-deletion warnings, and secret-specific diff
handling.

Planning must not touch the Git working tree. Change lists must omit eager patch
generation; the selected file's textual diff is loaded through a separate,
locked request.

Destructive confirmation remains appropriate for:

- memory-file deletion;
- replacement of protected memory files;
- large deletion batches;
- removal of legacy `_sync/**` content during the next payload build.

### Use asymmetric, explicit resolution

Outgoing local changes may be discarded per file by restoring the selected path
from the committed payload and applying that path locally. This does not advance
repository state and must leave every other outgoing change pending.

Incoming changes remain bulk-only because Git fast-forward pull advances the
repository as a whole. The review UI keeps files collapsed and loads only the
selected file's diff on demand. Resolution is one of:

- pull the complete cloud payload;
- discard one outgoing local change;
- discard all outgoing changes and restore the committed payload locally;
- keep the plan unresolved.

Automatic sync must block whenever incoming and outgoing file changes coexist,
even if destructive confirmation was supplied. It must never restore a complete
local snapshot over newly pulled incoming files.

## HTTP API cleanup

Remove the following route handlers and routes:

```text
/sync/shibboleth/unlock
/sync/shibboleth/lock
/sync/secrets/enable
/sync/secrets/disable
/sync/secrets/unlock
/sync/secrets/rotate
/sync/secrets/register-device
/sync/secrets/generate-mnemonic
/sync/secrets/check-mnemonic
/sync/secrets/synced-keys
/sync/secrets/remove-keys
```

Remove `_shibboleth_from_payload`. Pull, push, and automatic-sync requests must
not accept passphrases or mnemonics.

Also remove the unused `/sync/ahead-behind` and conflict-preview endpoints.
Mixed changes are handled solely by the explicit review flow; no agent conflict
resolver or `auto_resolve_enabled` profile option remains.

Keep the file-sync routes:

```text
/sync/status
/sync/plan
/sync/pull
/sync/push
/sync/auto
/sync/auto/run
/sync/discard-outgoing
```

## Frontend cleanup

Delete:

```text
frontend/src/components/settings/ShibbolethPanel.tsx
```

From `GitHubSyncSection.tsx`, remove:

- the shared-key-vault panel;
- unlock requirements before file operations;
- secret categories and labels;
- key import/export notifications;
- vault-inventory and key-selection state;
- Shibboleth and mnemonic API calls.

The GitHub sync card should state, through i18n:

> Syncs config, skills, and memory. API keys and credentials stay on this device.

The action bar should follow the file plan: show **Pull** only when incoming
files exist, show **Push** only when outgoing files exist, and hide both when
the repository is current. Do not retain a separate combined Sync button;
mixed changes belong in the explicit review flow.

From `frontend/src/lib/dataApi.ts`, remove secret-vault types, secret-sync profile
fields, secret-management functions, and Shibboleth arguments on pull and push.
Remove the payload inventory and revision UUID display; both duplicate Git state
and require unnecessary full-payload work during status loading.

Remove obsolete Shibboleth translations from the English and Chinese message
files. Add translations for the file-only scope statement and any legacy-bundle
warning.

## Legacy encrypted bundles

The new sync workflow must never decrypt, import, update, or create
`_sync/secrets/**`.

This feature has not been part of the stable file-sync contract, so payload
construction removes a legacy encrypted bundle directly. Documentation must
explain that deleting the current file does not remove ciphertext from Git
history and should recommend rotating provider keys if the repository or
recovery phrase may have been exposed.

## Tests

Delete tests dedicated to the removed implementation:

```text
tests/sync/test_encrypted_secret_sync.py
tests/sync/test_shibboleth.py
```

Update route, payload, service, profile, and frontend tests for the reduced
schema and API.

Add real temporary-Git-repository coverage for:

1. Pushing local config, skill, and memory changes.
2. Pulling remote portable-file changes.
3. Excluding API keys and all machine-local secret files.
4. Ensuring planning does not change repository status.
5. Simultaneous incoming and outgoing changes.
6. Per-file outgoing discard preserving other outgoing changes.
7. Bulk pull and bulk discard resolution.
8. Requiring confirmation for protected memory deletion.
9. Removing a legacy encrypted bundle from newly built payloads.
10. Preventing auto-sync from overwriting unresolved incoming files.

Provider mocks remain useful for error-path unit tests, but reconciliation
semantics must be verified against real Git repositories.

## Suggested commit sequence

1. `test(sync): define file-only sync and secret exclusion`
2. `refactor(sync): remove encrypted key models and services`
3. `refactor(sync): make file planning read-only`
4. `refactor(sync): simplify file sync routes and responses`
5. `refactor(frontend): remove shared key vault UI`
6. `test(sync): cover mixed Git reconciliation and outgoing file discard`
7. `docs(sync): document device-local credentials`

## Acceptance criteria

- No API-key value or encrypted key bundle is created by sync.
- No Shibboleth, mnemonic, vault, or encrypted-secret runtime code remains.
- Planning is read-only.
- GitHub sync does not require an unlock step.
- The UI accurately describes the synchronized file categories.
- Mixed incoming and outgoing changes remain blocked until explicitly resolved.
- Mixed incoming and outgoing changes are covered by real Git tests.
- The full non-sandbox test suite passes.
- Ruff, the frontend production build, and pre-commit pass.
- A repository-wide search for removed terminology returns only intentional
  migration documentation.

## Follow-up

Add a separate secret-provider subsystem after this pull request. The first
optional implementation may use the official Bitwarden CLI with a configurable
server URL, allowing both Bitwarden and Vaultwarden deployments. Only secret
references should participate in portable-file sync.
