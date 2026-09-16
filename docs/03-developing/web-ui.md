---
sidebar_position: 6
---

# Running the web UI

Suzent normally runs as a desktop app: a Tauri shell that starts the Python
backend and loads the frontend inside a webview. The same frontend bundle also
runs in an ordinary browser, served by the backend itself.

```bash
suzent web
```

There is no second process and no second port. The web UI is a route set on the
ordinary backend, so whatever already serves the API serves the UI too, from one
origin — which is what lets the frontend use relative URLs and keep working
behind a reverse proxy or a tunnel.

## The backend is a service, not something you launch

`suzent web` does not start a server of its own. It makes sure *something* is
serving and then opens the browser:

| Situation | What happens |
| --- | --- |
| The background service is running | Opens its URL |
| The service is installed but stopped | Starts it, waits for readiness, opens |
| Another backend is already up (`suzent serve`, or the desktop app's) | Reuses it |
| Nothing is installed or running | Offers to install the service (`--install` / `--no-install` to decide non-interactively) |

Installing the service is the point: it starts at login, a supervisor restarts
it if it crashes, and it outlives every terminal and window. After that the
browser tab is the only thing you ever open — `suzent web` just points at it.
Manage it with `suzent service status | start | stop | logs | doctor`, or from
**Settings → Background service** in the desktop app.

The service binds `127.0.0.1:25314` and holds an instance lock on that port, so
a second backend cannot quietly shadow it.

### One-off servers

`suzent web --foreground` runs a throwaway backend tied to the terminal, which
is what `--port`, `--host` and `--debug` apply to. Use it for development, or
for a binding where a login-persistent service would be the wrong thing to
install.

## Building the bundle

The UI ships inside the Python package at `suzent/webui/`. It is a build
artifact, so a source checkout has to produce it once:

```bash
python scripts/build_webui.py
```

That runs `npm run build` in `frontend/` and copies `frontend/dist` into
`src/suzent/webui/`. Pass `--no-build` to stage an existing `frontend/dist`.
Without it, `suzent web` reports that no UI is built in and the backend simply
serves the API.

During frontend development you do not need this: `npm run dev` in `frontend/`
serves the UI on `http://127.0.0.1:18080` and talks to the backend on port
25314.

## Desktop-only features

The frontend detects its host with `isDesktop()` / `isWeb()` in
`frontend/src/lib/runtime.ts`. A browser has no Tauri internals, so these are
gated:

| Feature | In a browser |
| --- | --- |
| Window controls (minimize / maximize / close) | Hidden; the browser draws its own chrome |
| Background service settings | The settings category is hidden |
| Self-update | Reports "nothing available"; update the backend instead |
| Native folder picker | Replaced by a picker that browses the host through `/system/files` |
| Native drag-and-drop of files | Falls back to the ordinary HTML5 drop handlers |
| Restart after a network-binding change | You restart the backend yourself |

Never call a `@tauri-apps/*` API without a guard: `invoke` throws
*synchronously* when the Tauri internals are absent, so a `.catch()` on its
promise does not contain the error.

## Serving it somewhere other than loopback

Requests from `127.0.0.1` are trusted. Anything else is a remote caller and has
to present a device token — the same rule that protects the API when the node
mesh binds the LAN. A browser on another machine is no exception.

The static bundle itself (`/`, `/assets/…`) is served without a token: it is the
same public bundle the desktop app ships and carries no secrets. Every API call
it makes still needs one.

1. Mint a host-scope token (`POST /nodes/host-token`, or approve the device in
   **Settings → Devices**).
2. Open the UI once with the token on the URL:
   `https://your-host/?token=<token>`.

The frontend consumes the token, strips it from the address bar, and stores it
in `localStorage`. From then on every `fetch` carries it as a bearer header.
The two SSE endpoints (`/events/stream`, `/subagents/stream`) accept it as a
query parameter instead, because `EventSource` cannot set request headers.

### Environment variables

| Variable | Effect |
| --- | --- |
| `SUZENT_SERVE_HEADLESS=1` | Do not serve the UI; API only |
| `SUZENT_ALLOWED_ORIGINS` | Extra origins allowed to make cross-origin API calls, comma-separated |
| `SUZENT_ALLOWED_HOSTS` | Extra `Host` header values accepted from loopback clients — needed when a reverse proxy on the same machine fronts Suzent under a domain name |

`SUZENT_ALLOWED_HOSTS` exists because a loopback request carrying an unknown
`Host` is how DNS rebinding looks: a page on an attacker's domain, rebound to
`127.0.0.1`, is same-origin with the backend and so escapes CORS entirely.
Suzent answers those with `421 Misdirected Request`.

## Serving the bundle yourself

If you would rather put the UI behind your own static host or CDN, set
`SUZENT_SERVE_HEADLESS=1`, serve `frontend/dist` from wherever you like, and add
that origin to `SUZENT_ALLOWED_ORIGINS` so the browser may call the API
cross-origin.
