---
sidebar_position: 11
---

# Desktop shell

The desktop app is a window over the local Python backend. The shell starts or
attaches to the backend, serves the React frontend, and supplies what a browser
cannot: a tray icon, native notifications, global shortcuts, file dialogs and
embedded web pages.

Suzent is moving its shell from Tauri (`src-tauri/`) to Electron
(`apps/desktop/`) so every platform renders with the same Chromium engine; see
the roadmap for the remaining steps. Until the switch, both shells build from
the same frontend.

## Talking to the shell

The frontend never imports a shell API directly. `frontend/src/lib/desktop.ts`
is the only bridge: `invoke(command, args)`, `listen(event, callback)`, window
controls, `openUrl`, `openDialog`, global shortcuts and notification
permission. Under Electron it calls `window.suzentDesktop`, which the sandboxed
preload (`apps/desktop/src/preload.ts`) exposes; under Tauri it calls
`@tauri-apps/*`. Both shells answer the same command names (`get_backend_port`,
`frontend_ready`, `get_service_status`, `resolve_close` and so on), so a
component works in either. Gate every call on `isDesktop()`: the same bundle
also runs as the web UI.

Window dragging differs: Tauri needs a `startDragging()` call on mouse down,
while Electron drags through CSS. Mark draggable areas with
`data-tauri-drag-region` (the element itself) or `data-window-drag` (an area
with controls inside); `styles.css` turns both into `app-region: drag` under
Electron and keeps buttons, links, inputs and anything with `[data-no-drag]`
clickable.

## Runtime layouts

`apps/desktop/src/layout.ts` decides where the backend comes from:

- **Bundled** (an installed app): `<resources>/runtime/python` is a
  relocatable CPython with Suzent installed, and `<resources>/suzent` holds
  the read-only `config/`, `skills/`, `plugins/` and browser extension, passed
  to the backend as `SUZENT_PROJECT_DIR`. This is the layout the Microsoft
  Store package already uses.
- **Source** (development): the checkout that contains `apps/desktop`, or
  `SUZENT_DIR`. The backend runs from the checkout's `.venv`, or `uv run` when
  there is none.

Writable state always lives in the data dir (`~/.suzent`, or
`SUZENT_DATA_DIR`).

## Backend lifecycle

On start the shell tries to attach to a healthy backend on `SUZENT_PORT` or
the background service port (25314). It only attaches to one that belongs to
this install: a bundled app accepts another bundled backend of the same
version, a development run only one started from the same checkout. A
different Suzent on that port is reported, never stopped. Otherwise it starts
an owned child with `SUZENT_RUN_MODE=desktop-child`, waits for
`runtime/server.port`, then for `/health`, and injects the port into the page.
Quitting asks an owned backend to stop through `/service/stop` with a
per-launch token, then kills it if it has not exited after 15 seconds.

The page is served from `suzent://app`, a privileged custom scheme, with the
same Content Security Policy the Tauri build used. The backend's CORS policy
and browser-extension setup trust that origin alongside the Tauri ones.

## Closing and the tray

On Windows and macOS closing the window asks, hides to the tray, or quits,
per the saved choice in `~/.suzent/desktop/close-action`. Linux has no tray,
so closing quits. Quit, Dock Quit, Cmd+Q and restarts all pass through
`before-quit`, which marks the app as exiting so the close they cause is not
turned into a hide. The tray polls `/focal/chats` every four seconds and
shows chats waiting on the user and chats running; on Windows the icon gets a
red dot when something waits.

## Development

```bash
uv sync
(cd frontend && npm ci && npm run build)
cd apps/desktop
npm ci
npm run dev                 # builds and opens the app on the frontend build
SUZENT_DEV_URL=http://127.0.0.1:18080 npm run dev   # against `npm run dev` in frontend/
npm test                    # unit tests (node:test)
npm run e2e                 # starts the app and its backend, checks it, quits
```

`npm run e2e -- --app <packaged executable>` runs the same smoke test
against an installed build. CI runs the unit and smoke tests on Linux, Windows
and macOS.
