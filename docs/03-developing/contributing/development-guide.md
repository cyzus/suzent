---
sidebar_position: 1
---

# Development Guide

## Quick Start

Get SUZENT running in development mode in under 2 minutes.

```bash
# 1. Install Python dependencies (including dev + social extras)
uv sync --all-extras

# 2. Launch the full development environment (backend + desktop window)
uv run suzent start --dev
```

> **Note**: `suzent start` launches a built desktop app; it never implicitly
> enters development mode. Use `--dev` for the debug backend + Tauri dev.
> For a headless debug backend only, use
> `uv run suzent serve --debug`.

To update an existing development checkout, run:

```bash
uv run suzent update
```

This fast-forwards the current branch from its configured upstream and installs the Python and frontend
dependencies from the lockfiles. Suzent detects that this is a source checkout
and selects the development channel automatically. Bootstrapped installations
continue to use the stable channel.

CLI development updates require a clean working tree and a configured upstream.
Untracked files, unfinished Git operations, detached HEAD, or divergent history
must be handled manually. Updates do not switch branches or stash your work.

Alternatively, select your existing checkout in the installer and click **Update
this workspace**. This runs the standalone updater, not copied shell commands:
it fetches the current branch's upstream, pins the commit, stops this installation,
fast-forwards the same branch, synchronizes the existing `.venv`, and rebuilds
both daily desktop launch targets. Node.js/npm, Rust, uv, and the platform build
tools must already be available. Finish any development/watch tasks before updating.

Local changes or attached-branch Git conflicts require **Back up and update**
confirmation. The updater verifies a snapshot under the existing
`<checkout>/.suzent/update-recovery/` directory before clearing tracked changes;
changes are not automatically reapplied. Ignored data and untracked working files
are not deleted; a file blocking the fast-forward stops the update safely.
Detached checkouts/rebases, missing upstreams, and diverged branches still require
manual attention. Failed updates restore source, locked Python dependencies, and
desktop backups, or retain the journal and report that repair is required. Use the
installer's repair button for an interrupted operation. Database changes are not
covered by source rollback.

### One checkout for development and daily use

Keep your chosen installation directory and its single `.venv`. Run
`suzent start --dev` for development, or build the desktop with
`npm run build:dist` in `src-tauri` and use `suzent start` for daily use.
Stop the existing backend and its background service before switching modes.
The update channel does not select the launch mode.

Installer branch selections (`--branch` or `SUZENT_BRANCH`) build the desktop
from that checkout instead of downloading a release desktop. Node.js/npm, Rust,
and the platform's Tauri build prerequisites must be installed. A failed build
stops the desktop stage rather than silently installing a mismatched binary.

Both modes use the current Python source and dependencies; daily mode is not
an isolated stable version. After manually checking out another revision,
sync its locked dependencies and rebuild the desktop before launching.
Save local changes first and back up user data before migrations: checking out
old source does not roll back a database. A saved custom installation path is
retained even if its environment is broken; repair that location rather than
silently installing another copy in the default user directory.

`uv sync --all-extras` installs both the `social` and `dev` optional
dependency groups (equivalent to the `all` extra). For a minimal runtime
without dev tooling, use `uv sync --extra social`.

To run the backend and frontend in separate terminals instead, see
[Development Modes](#development-modes) below.

## Prerequisites

### Required for All Development

- **Node.js** 20.x or higher
- **Python** 3.12 or higher

### Required for Desktop App Mode

- **Rust** 1.75 or higher
  ```bash
  # Windows
  winget install --id Rustlang.Rustup

  # Or download from https://rustup.rs/
  ```

### Platform-Specific Requirements

**Windows**
- Microsoft Visual C++ Build Tools
- WebView2 Runtime (usually pre-installed on Windows 10/11)

**macOS**
```bash
xcode-select --install
```

**Linux (Ubuntu/Debian)**
```bash
sudo apt-get update
sudo apt-get install -y libgtk-3-dev libwebkit2gtk-4.0-dev \
  libappindicator3-dev librsvg2-dev patchelf
```

## Development Modes

### Desktop App Mode

Uses Tauri to create a native desktop window. Requires Rust.

> Install Python dependencies first with `uv sync --all-extras` (see [Quick Start](#quick-start)).

**Terminal 1** - Start Python backend:
```bash
uv run python src/suzent/server.py
```

Expected output:
```
INFO:     Starting Suzent server on http://127.0.0.1:25314
INFO:     Application startup complete.
```

**Terminal 2** - Start Tauri:
```bash
cd src-tauri
npm install
npm run dev
```

This will:
1. Start Vite dev server (frontend)
2. Compile the Rust code (first time only, takes a few minutes)
3. Open a native desktop window
4. Frontend connects to backend

### Local Ports

Default local endpoints for development:

- Backend API: `http://127.0.0.1:25314`
- Frontend dev server: `http://127.0.0.1:18080`

To avoid Windows reserved-port conflicts, frontend port values are sourced from:

- `frontend/vite.config.ts` (`server.port`)
- `src-tauri/tauri.conf.json` (`build.devUrl`)


## Configuration

### Development vs Production

| Config File | Mode | Backend |
|-------------|------|---------|
| `tauri.conf.json` | Development | External (port 25314) |
| `tauri.conf.prod.json` | Production | Bundled Python + uv venv |

**Development mode** (`npm run dev`):
- No bundled backend - expects backend running on the local API endpoint
- Frontend hot-reload enabled
- DevTools available (right-click in window)

**Production mode** (`npm run build`):
- Bundles Python runtime + uv + suzent wheel as resources
- Creates venv on first launch, then auto-starts backend on dynamic port
- All assets bundled into single installer

### Environment Variables

The backend automatically detects bundled environment through:

| Variable | Purpose |
|----------|---------|
| `SUZENT_PORT` | Dynamically assigned port (0 = OS picks) |
| `SUZENT_HOST` | Bound to `127.0.0.1` in production |
| `SUZENT_DATA_DIR` | User data directory (defaults to `~/.suzent`) |
| `CHATS_DB_PATH` | SQLite database path |
| `LANCEDB_URI` | LanceDB vector store path |
| `SANDBOX_DATA_PATH` | Sandbox data directory |
| `SKILLS_DIR` | Advanced extra skills directory override |
| `SUZENT_CAPABILITIES_TO_REPO` | Explicit maintainer opt-in that writes capability data into tracked `config/capabilities/` files instead of the user-data overlay. Normal and developer modes do not set it. See [Model Capabilities](../architecture/model-capabilities.md). |

### Tauri Configuration

Edit `src-tauri/tauri.conf.json` to customize:
- Window size and behavior
- Application name and version
- Bundle settings
- Security policies

## Hot Reload Behavior

| Component | Hot reload | Action on change |
|-----------|------------|------------------|
| Frontend (React) | Yes | Automatic |
| Backend (Python) | No | Restart manually |
| Rust code | No | Restart Tauri |

## Architecture Notes

Suzent uses `pydantic-ai` directly for provider execution, streaming, history
processing, and deferred tool discovery, but keeps product-specific wrappers
where they preserve local behavior. Tools still route through Suzent's registry,
permission engine, sandbox/path policy, frontend events, and persisted replay
contracts before execution.

Do not replace shell, filesystem, MCP, web, image, or skill behavior with a
native provider primitive unless the replacement preserves cross-provider
fallback, permission policy, cancellation, persisted tool-call replay, and the
existing frontend event contract.

## Command Reference

| Task | Command |
|------|---------|
| Install dependencies | `uv sync --all-extras` |
| Start backend | `uv run python src/suzent/server.py` |
| Start Tauri dev | `cd src-tauri && npm run dev` |
| Bundle Python backend | `python scripts/bundle_python.py` |
| Build full app | `cd src-tauri && npm run build:full` |
| Build Tauri only | `cd src-tauri && npm run build` |

## Production Build

Build the complete standalone application:

```bash
cd src-tauri
npm run build:full
```

This automatically bundles the Python runtime, uv, and suzent wheel, then builds the Tauri application.

**Convenience scripts:**

```powershell
# Windows
.\scripts\build_tauri.ps1
```

```bash
# macOS / Linux
./scripts/build_tauri.sh
```

### Build Artifacts

| Platform | Location |
|----------|----------|
| Windows | `src-tauri/target/release/bundle/msi/SUZENT_x.x.x_x64_en-US.msi` |
| macOS | `src-tauri/target/release/bundle/dmg/SUZENT_x.x.x_x64.dmg` |
| Linux | `src-tauri/target/release/bundle/appimage/suzent_x.x.x_amd64.AppImage` |

**Bundle size** — the bundled app is 80–150 MB (Python runtime, uv, LanceDB).
Playwright/Chromium (~300 MB) is downloaded separately on first launch.

## Desktop App Architecture

```
+-------------------------------------------+
|           Tauri Application               |
|  +--------------+    +------------------+ |
|  |   Webview    |    |  Rust Process    | |
|  |   (React)    |    |  - Backend       | |
|  |  Frontend    |--->|    Lifecycle     | |
|  |  Built       |    |  - Port Mgmt     | |
|  |  Assets      |    |  - First-Run     | |
|  +--------------+    |    Setup         | |
|         |            +------------------+ |
|         +-----HTTP API------+             |
|             (localhost:dynamic)           |
+-------------------------------------------+
                    |
            +-------v--------+
            | Python Backend |
            | (uv-managed    |
            |  venv)         |
            +----------------+
```

## First-Run Behavior

When the desktop app launches for the first time (or after an update):

1. **Venv Creation** (~10–30 seconds): Rust runs `uv venv` with bundled Python, then installs the suzent wheel. A version marker prevents re-running on subsequent launches.
2. **Playwright Install** (~1–2 minutes): Chromium is downloaded for the browsing tool. Non-fatal — retries on first use if it fails.
3. **Config Sync**: Example configs and skills are copied to the app data directory. Existing files are preserved.

## Application Data Location

| Platform | Location |
|----------|----------|
| Windows | `%APPDATA%\com.suzent.app\` |
| macOS | `~/Library/Application Support/com.suzent.app/` |
| Linux | `~/.config/com.suzent.app/` |

Contents: `backend-venv/`, `chats.db`, `memory/`, `skills/`, `sandbox-data/`, `config/`

## Logo standard

Use [`SuzentLogo`](../../../frontend/src/components/SuzentLogo.tsx) for UI placements:

```tsx
import { SuzentLogo } from '@/components/SuzentLogo';

<SuzentLogo className="h-7 w-7" />
<SuzentLogo className="h-7 w-7" interactive />
```

`className` controls size; `interactive` defaults to false and enables cursor-following
eyes. Use 28 px (`h-7 w-7`) in headers and 64 px or larger on splash screens.
Avoid interactive instances in large lists.

The canonical 24 × 24 geometry is a black rounded square (`rx=4`) with white
5 × 5 eyes at `(5,8)` and `(14,8)`, each with `rx=1.5`. Change the component first,
then synchronize `frontend/public/favicon.svg` and the `RobotFace` primitive in
`frontend/src/components/chat/RobotAvatar.tsx`. RobotAvatar retains its own
primitive for its animation variants. Do not inline new copies of the logo or
add an outer white border.

## Memory implementation

Memory documentation has one entry point under [Memory](../../02-concepts/memory/README.md).
Contributors should read [Architecture](../architecture/memory-architecture.md)
for invariants and [Internals](../architecture/memory-internals.md) for classes,
storage layout, and failure behavior.

## Troubleshooting

### Backend Issues

**"resource path doesn't exist" during `npm run dev`**

This is expected. Development mode does not use the bundled backend. Start the Python backend manually:
```bash
python src/suzent/server.py
```

**Backend not responding**

Verify backend is running:
```bash
curl http://localhost:25314/config
```
Should return JSON configuration.

### Rust/Tauri Issues

**"cargo: command not found"**

Install Rust from https://rustup.rs/ and restart your terminal.

**Cargo build fails**

Update Rust and clean the build:
```bash
rustup update
cd src-tauri && cargo clean
```

### Frontend Issues

**Frontend shows connection errors**

1. Verify backend is running: `curl http://localhost:25314/config`
2. Check browser console for the actual error
3. Ensure CORS is working (should be by default)

**Changes not appearing**

- Frontend changes: Should auto-reload. Try hard refresh (Ctrl+Shift+R).
- Backend changes: Restart the backend (Ctrl+C, then restart).
- Rust changes: Restart Tauri dev server.

### Built App Issues

**Bundle script fails — missing `build` package:**
```bash
uv pip install build
```

**Backend fails to start in the built app**

- Check `~/suzent_startup.log` for startup logs.
- Delete `backend-venv/` in the [app data directory](#application-data-location) to force
  venv re-creation on the next launch.

### General Issues

**First build is very slow**

The first Rust build takes 5-10 minutes to compile all dependencies. Subsequent builds are faster due to caching.
