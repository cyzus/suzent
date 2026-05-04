# User Home Data Directory, Import/Export, and Sync Plan

## Goal

Move SUZENT user data out of the source checkout and into the user's home directory by default, while keeping the location configurable and adding clear import, export, and sync workflows.

Default data directory:

```text
Windows: C:\Users\<User>\.suzent
macOS:   /Users/<User>/.suzent
Linux:   /home/<User>/.suzent
```

Users can override the location with:

```text
SUZENT_DATA_DIR=/custom/path
```

The repository should contain source code, examples, docs, and bundled skills. Runtime data should live in the user data directory.

## Non-Goals

- Do not implement real-time multi-device database replication in the first pass.
- Do not sync machine-local runtime files such as active port files, logs, lock files, or process state.
- Do not move bundled repository assets such as `skills/`, `config/default.example.yaml`, or docs into the user data directory.
- Do not silently overwrite existing user data during import or migration.
- Do not make users choose individual backup categories in the first pass; exports should be complete portable snapshots by default.

## Directory Layout

Use `~/.suzent` as the logical root:

```text
~/.suzent/
  chats.db
  memory/
  transcripts/
  state/
  sandbox/
    shared/
    sessions/
  skills/
    my-custom-skill/
      SKILL.md
  config/
    default.yaml
    providers.local.json
    permissions.yaml
    skills.json
  exports/
  runtime/
    server.port
    server.log
    locks/
  cache/
```

Data that should be exportable or syncable:

```text
chats.db
memory/
transcripts/
state/
sandbox/
skills/
config/
```

Data that should stay machine-local:

```text
runtime/
cache/
*.log
*.port
*.lock
```

Exports should include the whole portable data tree by default, including `sandbox/shared/` and `sandbox/sessions/`. Only machine-local runtime state and rebuildable caches should be excluded.

## Skills Layers

Skills should follow the same source-vs-user split as configuration:

```text
Repository built-in skills:
  PROJECT_DIR/skills/

User-installed skills:
  ~/.suzent/skills/
```

Suggested precedence:

```text
1. Repository built-in skills
2. User-installed skills under ~/.suzent/skills/
3. SKILLS_DIR override, for advanced users
```

User skills should override built-in skills by skill metadata name. For example, if both `PROJECT_DIR/skills/notebook/SKILL.md` and `~/.suzent/skills/notebook/SKILL.md` exist, the user version wins.

Implementation notes:

- Replace the current single-directory `SkillLoader` with a layered loader that accepts multiple roots.
- Store enabled skill state in `~/.suzent/config/skills.json`, not `PROJECT_DIR/config/skills.json`.
- Include `~/.suzent/skills/` and `~/.suzent/config/skills.json` in export/sync.
- Do not copy built-in repo skills into `~/.suzent/skills/` on first run.
- Frontend copy should say user skills belong in `~/.suzent/skills/`, while built-in skills are bundled with SUZENT.
- Keep `SKILLS_DIR` as an advanced override. If set, it can either replace the default layered roots or be appended as the highest-priority root; choose and document one behavior during implementation.

Sandbox mounting:

- Agents should continue to see skills at `/mnt/skills/{skill-name}/`.
- Because Docker bind mounts map one host path to `/mnt/skills`, build a generated merged skills directory under `~/.suzent/runtime/skills_merged/`.
- Populate that directory from the layered skill index, with user skills overriding built-ins.
- Mount `~/.suzent/runtime/skills_merged/` read-only at `/mnt/skills`.
- Treat this merged directory as rebuildable runtime state and exclude it from export/sync.

## Configuration Layers

Configuration should support multiple layers. User-level files under `~/.suzent/config/` have the highest priority.

Suggested precedence, from lowest to highest:

```text
1. Repository examples and defaults
   config/default.example.yaml
   config/providers.json
   config/permissions.example.yaml

2. Repository local overrides
   config/default.yaml
   config/permissions.yaml

3. User data directory overrides
   ~/.suzent/config/default.yaml
   ~/.suzent/config/providers.local.json
   ~/.suzent/config/permissions.yaml

4. Environment variables
   SUZENT_DATA_DIR, SUZENT_PORT, SUZENT_HOST, provider keys, etc.

5. Runtime/database-backed settings
   User preferences, provider selections, MCP servers, role model choices
```

First run behavior:

- Do not copy every repository config file blindly.
- Create `~/.suzent/config/` if missing.
- Optionally create minimal user override files only when the user changes settings.
- Keep repo examples as templates and fallback defaults.
- Treat `~/.suzent/config/` as portable user intent and include it in export/sync.

This keeps source checkout defaults upgradeable while giving the user directory final authority.

## Backend Plan

### 1. Centralize path resolution

Update `src/suzent/config/__init__.py`:

- Keep `PROJECT_DIR` as the source checkout root.
- Add `get_data_dir() -> Path`.
- Add `DATA_DIR = get_data_dir()`.
- Add `RUNTIME_DIR = DATA_DIR / "runtime"`.
- Add `CACHE_DIR = DATA_DIR / "cache"`.
- Prefer `SUZENT_DATA_DIR` when set.
- Default to `Path.home() / ".suzent"`.
- Replace current `SUZENT_APP_DATA` usage with `SUZENT_DATA_DIR`.
- Remove `SUZENT_APP_DATA` immediately unless implementation discovers a hidden external dependency. Current source usage is small and not wired through current Tauri source.

Expected precedence:

```text
1. SUZENT_DATA_DIR
2. Path.home() / ".suzent"
```

### 2. Migrate old repository `.suzent`

Add a small migration module, for example:

```text
src/suzent/core/data_migration.py
```

Behavior:

- Detect legacy `PROJECT_DIR / ".suzent"`.
- If `DATA_DIR` is empty, copy legacy data to `DATA_DIR`.
- Verify key files/directories after copy.
- Rename old directory to `.suzent.backup` when possible, or leave a `MIGRATED.md` marker if rename is unsafe.
- Never delete user data automatically.
- Log clear `INFO` lifecycle messages and `WARNING` recoverable migration issues.

Run migration once during backend startup before database initialization.

### 3. Update all data consumers

Ensure these continue to use `DATA_DIR` or `RUNTIME_DIR`:

- Chat database: `chats.db`
- LanceDB memory: `memory/`
- Transcripts: `transcripts/`
- State mirror: `state/`
- Sandbox data: `sandbox/`
- User skills: `skills/`
- Skills enabled state: `config/skills.json`
- Server port file: `runtime/server.port`
- Server log file: `runtime/server.log`

Avoid hardcoded `.suzent` paths in Python code.

### 4. Add import/export services

Add a backend service, for example:

```text
src/suzent/core/data_portability.py
```

Export:

- Create a zip archive.
- Include a `manifest.json`.
- Include only portable data.
- Include `sandbox/` by default, including per-session data.
- Exclude runtime, cache, locks, active logs, and port files.
- Support secure API key export when explicitly requested.

Import:

- Validate manifest.
- Support `dry_run`.
- Support first-pass mode: `replace`.
- Always create a timestamped backup before replacing existing data.
- Refuse import while another SUZENT process holds the data lock.
- Detect whether imported database files require schema upgrades and run migrations automatically on next backend startup.
- After replacing a live `chats.db`, prefer a controlled backend restart or maintenance mode rather than continuing with stale in-process database handles.
- For `suzent upgrade`, run data directory migration and database migrations while the service is stopped. In that flow no app restart prompt should be needed because startup happens after migration.

API key export:

- Default export should exclude secrets.
- Add an explicit `--include-secrets` CLI flag and matching frontend confirmation.
- Secrets must be encrypted in the export archive.
- Use the existing `cryptography` dependency for portable secret export.
- Recommended format: passphrase-based encryption with `cryptography.hazmat.primitives.kdf.scrypt.Scrypt` and `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- Avoid adding a new dependency for Argon2id unless future security requirements justify it.
- Never write plaintext secrets into `manifest.json`.
- Import should require the passphrase before restoring encrypted secrets.

Suggested manifest:

```json
{
  "app": "suzent",
  "format_version": 1,
  "created_at": "2026-05-04T00:00:00Z",
  "source_data_dir": "~/.suzent",
  "includes": [
    "chats.db",
    "memory",
    "transcripts",
    "state",
    "sandbox",
    "skills",
    "config"
  ]
}
```

### 5. Add CLI commands

Extend `src/suzent/cli/main.py` or add a dedicated `src/suzent/cli/data.py`:

```text
suzent data path
suzent data status
suzent data export --output <zip>
suzent data import <zip> --dry-run
suzent data import <zip> --mode replace
suzent data sync push --target <folder>
suzent data sync pull --target <folder>
```

First sync implementation can be snapshot-based:

- `push`: export to a sync folder with manifest and versioned archive.
- `pull`: import the newest valid snapshot after dry-run validation.

## Tauri Plan

Update Rust path handling in `src-tauri/src/backend.rs` and `src-tauri/src/main.rs`:

- Compute the same default data dir as Python: `home/.suzent`.
- Ensure `runtime/` exists before backend launch.
- Store `server.port` and `server.log` under `runtime/`.
- Pass `SUZENT_DATA_DIR` into the backend process.
- Continue using the repo directory as the process working directory so source installs still work.
- In dev mode, read the port from `SUZENT_DATA_DIR/runtime/server.port`.

This avoids the current release-mode pattern of `repo_dir.join(".suzent")`.

## Frontend Plan

### 1. Settings UI

Add a data management section to the settings modal:

```text
Settings -> Data
```

Controls:

- Show current data directory.
- Open data directory using Tauri shell/dialog capability.
- Export data.
- Import data.
- Run import dry-run and show a summary before applying.
- Show sync folder path if configured.
- Trigger snapshot push/pull sync.

Use existing settings component patterns and i18n messages.

### 2. API client

Add frontend API helpers, for example:

```text
frontend/src/lib/dataApi.ts
```

Endpoints should cover:

- `GET /data/path`
- `GET /data/status`
- `POST /data/export`
- `POST /data/import/dry-run`
- `POST /data/import`
- `POST /data/sync/push`
- `POST /data/sync/pull`

### 3. User-visible strings

Add all strings to:

```text
frontend/src/i18n/messages/en.ts
frontend/src/i18n/messages/zh-CN.ts
```

Avoid hardcoded user-visible strings in React components.

## API Plan

Add routes under:

```text
src/suzent/routes/data_routes.py
```

Endpoints:

```text
GET  /data/path
GET  /data/status
POST /data/export
POST /data/import/dry-run
POST /data/import
POST /data/sync/push
POST /data/sync/pull
```

Return structured pydantic models for:

- data directory info
- export result
- import dry-run result
- import result
- sync result

## Locking and Safety

Add a data lock under:

```text
~/.suzent/runtime/locks/data.lock
```

Use it for:

- import
- replace
- sync pull
- migration

Export can run while the app is active, but should warn if files change during archive creation. A later iteration can add SQLite backup APIs for cleaner live exports.

## Testing Plan

Backend tests:

- `get_data_dir()` honors `SUZENT_DATA_DIR`.
- Default path is `Path.home() / ".suzent"`.
- Legacy `.suzent` migration copies data when destination is empty.
- Migration does not overwrite existing data.
- Export manifest excludes runtime/cache/locks.
- Import dry-run validates archive without writing.
- Replace import creates backup first.

Tauri checks:

- Backend receives `SUZENT_DATA_DIR`.
- Port file is read from `runtime/server.port`.
- Logs are written to `runtime/server.log`.

Frontend tests:

- Data settings renders current path.
- Export/import buttons call the correct API helpers.
- Dry-run summary is displayed before destructive import.
- English and Chinese i18n keys exist.

Manual verification:

```text
uv run pytest -m "not sandbox"
npm --prefix frontend run build
```

## Rollout Plan

### Phase 1: Path foundation

- Add `SUZENT_DATA_DIR`.
- Default to `~/.suzent`.
- Move runtime files to `runtime/`.
- Keep compatibility with existing repo `.suzent`.
- Remove existing `SUZENT_APP_DATA` usage and replace it with `SUZENT_DATA_DIR`.
- Update docs.

### Phase 2: Migration

- Implement legacy repo `.suzent` migration.
- Add tests for safe copy and no-overwrite behavior.
- Add clear startup logs.

### Phase 3: Export/import

- Add data portability service.
- Add CLI commands.
- Add backend API routes.
- Add frontend settings UI.

### Phase 4: Snapshot sync

- Add snapshot push/pull sync.
- Add sync folder status.
- Add conflict detection through manifest timestamps and local backup creation.

### Phase 5: Merge sync

- Add selective merge for durable structured data.
- Keep SQLite/LanceDB file-level replacement behind explicit user confirmation.
- Consider markdown memory or event-log based sync as the long-term merge substrate.

## Documentation Updates

Update:

- `README.md`
- `docs/01-getting-started/quickstart.md`
- `docs/02-concepts/filesystem.md`
- `docs/02-concepts/memory/*`
- `docs/03-developing/development-guide.md`
- `docs/03-developing/desktop-guide.md`

Document:

- Default `~/.suzent` location.
- `SUZENT_DATA_DIR` override.
- Legacy migration behavior.
- What export includes and excludes.
- Snapshot sync limitations.

## Open Questions

None for the current planning pass.

Implementation note: `suzent upgrade` should perform migrations while SUZENT is stopped. Frontend-driven import can use maintenance mode plus backend restart if replace-mode import is added to the running desktop app.
