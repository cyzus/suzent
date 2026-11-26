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

`suzent start --dev` starts the debug backend, then runs the Electron shell in
`apps/desktop` on the Vite dev server, so frontend edits hot-reload in the
window. It installs the `frontend/` and `apps/desktop/` npm dependencies when
they are missing. `suzent stop` ends both.

Plain `suzent start` in a source checkout runs the same shell on the built web
UI (`frontend/dist`) instead; build it with `npm run build` in `frontend/` and
then in `apps/desktop/`. For a headless debug backend only, use
`uv run suzent serve --debug`.

To update an existing development checkout, run:

```bash
uv run suzent update
```

This fast-forwards the current branch from its configured upstream, installs the
Python and npm dependencies from the lockfiles, and rebuilds the web UI and the
desktop shell. Suzent detects that this is a source checkout and selects the
development channel automatically.

CLI development updates require a clean working tree and a configured upstream.
Untracked files, unfinished Git operations, detached HEAD, or divergent history
must be handled manually. Updates do not switch branches or stash your work.

`uv sync --all-extras` installs every optional dependency group (chat apps,
camera and `dev`; equivalent to the `all` extra). For a minimal runtime
without dev tooling, use `uv sync`; chat apps and the camera install their
packages when they are set up, as in a normal install.

To set up a fresh developer checkout with the setup script instead, run it with
`SUZENT_DEV_SETUP=1` and `--source`; it installs the npm dependencies and builds
the web UI and the desktop shell.

## Prerequisites

- **Node.js** 20.x or higher
- **Python** 3.12 or higher, managed with [uv](https://docs.astral.sh/uv/)

The desktop shell is Electron, so developing it needs no Rust toolchain or
platform webview packages. Rust is only needed to work on the setup window
(`apps/desktop-setup`), the Microsoft Store helper (`apps/desktop/store-cli`) or
the legacy Tauri code (`src-tauri`, `apps/suzent-installer`).

## Development Modes

### One command

```bash
uv run suzent start --dev
```

### Separate terminals

**Terminal 1** - Start Python backend:
```bash
uv run python src/suzent/server.py
```

Expected output:
```
INFO:     Starting Suzent server on http://127.0.0.1:25314
INFO:     Application startup complete.
```

**Terminal 2** - Start the desktop app (Electron):
```bash
cd apps/desktop
npm install
npm run dev
```

This will:
1. Compile the shell
2. Start the Vite dev server (frontend), or reuse one already running on port 18080
3. Open the desktop window on it, so frontend edits hot-reload
4. Attach to the backend from Terminal 1, or start one from the checkout if none is running

Closing the window also stops the Vite server it started. `npm start` opens the
shell on the last `frontend/dist` build instead.

### Browser only

`npm run dev` in `frontend/` serves the web console at `http://127.0.0.1:18080`
against the running backend. See [Web UI](web-ui.md).

### Local Ports

Default local endpoints for development:

- Backend API: `http://127.0.0.1:25314`
- Frontend dev server: `http://127.0.0.1:18080` (`server.port` in
  `frontend/vite.config.ts`, and `SUZENT_DEV_URL` for the shell)

## Configuration

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `SUZENT_PORT` | Backend port (0 = OS picks) |
| `SUZENT_HOST` | Bound to `127.0.0.1` in production |
| `SUZENT_DIR` | Source checkout the desktop shell runs the backend from |
| `SUZENT_DEV_URL` | Page the desktop shell loads instead of the built web UI |
| `SUZENT_DATA_DIR` | User data directory (defaults to `~/.suzent`) |
| `CHATS_DB_PATH` | SQLite database path |
| `LANCEDB_URI` | LanceDB vector store path |
| `SANDBOX_DATA_PATH` | Sandbox data directory |
| `SKILLS_DIR` | Advanced extra skills directory override |
| `SUZENT_CAPABILITIES_TO_REPO` | Explicit maintainer opt-in that writes capability data into tracked `config/capabilities/` files instead of the user-data overlay. Normal and developer modes do not set it. See [Model Capabilities](../architecture/model-capabilities.md). |

## Hot Reload Behavior

| Component | Hot reload | Action on change |
|-----------|------------|------------------|
| Frontend (React) | Yes | Automatic |
| Backend (Python) | No | Restart manually |
| Desktop shell (`apps/desktop/src`) | No | Run `npm run dev` again |

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
| Start everything for development | `uv run suzent start --dev` |
| Start the desktop shell with hot reload | `cd apps/desktop && npm run dev` |
| Run the shell's unit tests | `cd apps/desktop && npm test` |
| Build the bundled Python runtime | `uv run --no-project python scripts/build_desktop_runtime.py` |
| Build installers for this platform | `cd apps/desktop && npm run dist` |

## Installer Build

Release CI builds every installer (`.github/workflows/desktop-installers.yml`).
To build one locally for the platform you are on:

```bash
cd frontend && npm ci && npm run build && cd ..
uv run --no-project python scripts/build_desktop_runtime.py
cd apps/desktop && npm ci && npm run dist
```

The installers land in `apps/desktop/release/`. Each carries a relocatable
CPython with Suzent installed in it, so the app needs nothing else on the
machine. Data lives in `~/.suzent`, shared with every other way of running
Suzent. See [Desktop shell](../architecture/desktop-shell.md) for how the shell
finds its backend.

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

Memory documentation has one entry point under [Memory](../../03-features/memory/README.md).
Contributors should read [Architecture](../architecture/memory-architecture.md)
for invariants and [Internals](../architecture/memory-internals.md) for classes,
storage layout, and failure behavior.

## Troubleshooting

**Backend not responding**

Verify backend is running:
```bash
curl http://localhost:25314/config
```
Should return JSON configuration.

**Frontend shows connection errors**

1. Verify backend is running: `curl http://localhost:25314/config`
2. Open DevTools in the window and check the console for the actual error
3. Ensure CORS is working (should be by default)

**Changes not appearing**

- Frontend changes: Should auto-reload. Try a hard refresh (Ctrl+Shift+R).
- Backend changes: Restart the backend (Ctrl+C, then restart).
- Desktop shell changes: Close the window and run `npm run dev` again.

**`suzent start` says no desktop build was found**

Run `npm install` and `npm run build` in `frontend/` and then in
`apps/desktop/`, or use `suzent start --dev`.
