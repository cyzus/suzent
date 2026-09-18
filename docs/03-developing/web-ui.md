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

## The browser gets a console, not the desktop window

The desktop app is a chat window that keeps its operational surfaces folded
into a settings modal. That is the right shape when the machine is in front of
you. A browser session is the opposite case -- a headless host, reached from
somewhere else -- so the same bundle renders a different shell there:
`frontend/src/shells/WebShell.tsx`, chosen in `main.tsx` by `isWeb()`.

The console is a single left nav over a hash router (`wouter`): every page it
can reach is one grouped list of destinations, with chat at the top and each
settings category a route of its own (`#/providers`, `#/devices`, ...). The
retired `#/settings` redirects to `#/providers`. Collapsed it is an icon rail;
expanded it shows labels and group headings, and that choice is remembered.

Chat is the exception, because it is the one destination that brings a column of
its own. There the nav is the rail and nothing but the rail (`railOnly`): no
labels, no toggle, and a hairline instead of the heavy outer border, so the rail
and the conversation list beside it read as one navigation with a list in it
rather than as two sidebars. Two labelled columns before the conversation even
starts was the shape this replaced.

Destinations live in `frontend/src/shells/webRoutes.ts` -- one list, read by the
nav, the router and the tests.

The nav's footer carries the host it is talking to and its reachability. The
theme -- light, dark, or the machine's own setting -- is a setting like any
other and lives on the Appearance page (`#/appearance`), which is what a console
route can reach and the chat header is not; the header keeps its quick flip
between light and dark for the shell that draws it.

The console page replaces `<App>`'s own window rather than sitting beside it:
`ConsoleRoute` renders one `<App>` for chat and for the settings routes and
varies only its children, so moving between them keeps the tree -- the open
conversation and the providers under it -- instead of mounting a second copy of
the app. Chat's settings button navigates (`consolePathForCategory`) instead of
opening the desktop's modal; `ChatWindow` unmounts on the way, so the composer's
unsent text is held outside it and restored on return.

Two details are load-bearing:

- **Hash routing** (`#/devices`), not paths. The server only ever sees `/`, so
  no pre-auth route has to be exempted from the device-token check in
  `is_public_asset()`, and console navigation stays out of access logs.
- **Operations, Devices, Mesh, Usage and About mount outside `<App>`**, so they
  do not wait on its backend-readiness gate. A console opened against a
  struggling host still shows the pages you opened it to look at. Chat and the
  other settings categories do sit inside `<App>`: they need its provider stack,
  which needs the backend.

Everything under `components/`, `hooks/`, `lib/` and `i18n/` is shared by both
shells. The console reuses the settings tabs verbatim rather than restating
them.

## Operations over HTTP

The desktop app manages the background service through Tauri commands that
shell out to `suzent service`. A browser has no such bridge, and the browser is
exactly the client that needs one -- running a headless host from elsewhere is
mostly "is it up, why did it stop, restart it".

`src/suzent/routes/ops_routes.py` exposes that over HTTP, wrapping the same
`ServiceController` the CLI uses:

| Route | Does |
| --- | --- |
| `GET /ops/service/status` | Service status, plus `self_managed` and the log path |
| `GET /ops/logs?lines=N` | Tail of `server.log`, read backwards, capped at 2000 lines |
| `POST /ops/service/restart` | Restart the service |
| `POST /ops/service/enabled` | Install or uninstall it |

None of these are in `AGENT_ALLOWED_PATHS`, so a remote agent-scope token
cannot reach them; they need loopback or a full-scope token.

Two of them can act on the process serving the request, which is the normal
case on a headless host, and that shapes both:

- **Restart answers first.** When `self_managed` is true the route returns
  `202 {"status": "restarting"}` and defers the restart past the response.
  Restarting inline would kill the process mid-reply, and the console could not
  distinguish the restart it asked for from a host that fell over. The page
  then polls `/ops/service/status` until the host answers again.
- **Disabling yourself is refused** with `409 would_disable_self`. The call
  would succeed and take the console permanently offline: re-enabling needs a
  shell on the host, which is the one thing a remote browser does not have.
  Run `suzent service uninstall` there instead.

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

### The backend keeps it up to date

Nothing in the edit-and-refresh loop regenerates that bundle, so a checkout will
serve a frontend from weeks ago and give no sign of it -- the code is right, the
page is old, and the obvious conclusion is that the change did not work.

So `src/suzent/webui_build.py` checks, at startup and on each page load, whether
anything under `frontend/` is newer than the staged `index.html`, and runs the
build script on a worker thread when it is. The request still gets the bundle
that exists now; the log says what happened:

```text
Web UI bundle is out of date; rebuilding from D:\workspace\suzentrontend
Web UI rebuilt in 15s; refresh the page to pick it up
```

The scan skips `node_modules/` and `dist/`, is rate-limited to once every two
seconds, never runs two builds at once, and does not retry a failed build until
the source changes again. It only ever happens in a source checkout that has
`frontend/` and npm: an installed wheel carries a prebuilt bundle and finds
nothing to do. `SUZENT_AUTO_BUILD_WEBUI=0` turns it off.

One case it cannot fix from inside: the routes that serve the bundle are
registered when the app is built, so a *first* build -- where there was no
bundle at startup -- is served from the next restart rather than the current
process.

During frontend development you do not need any of this -- see below.

## Developing against it

`npm run dev` in `frontend/` (or `npm run dev` in `src-tauri/`, which starts the
same Vite server before opening the Tauri window) serves the UI on
`http://127.0.0.1:18080`. One server, both shells:

- the **Tauri window** gets the desktop shell, because `window.__TAURI__` is set
- a **browser tab** at `http://127.0.0.1:18080` gets the console

You can keep both open against the same Vite process and watch a change land in
each at once, which is the cheapest way to see where the two shells differ.

The browser tab still has to know which backend to call -- the desktop window is
handed its port at runtime, and a tab has no such channel -- but it works this
out for itself. `frontend/devBackend.ts` runs when the dev server starts and
looks for a backend that is already running, so developing on the console does
not mean starting a second one that fights the first for the channel
connections. In order:

1. `VITE_SUZENT_BACKEND`, if you set it
2. the port in `~/.suzent/runtime/service.json`, written by the installed service
3. `SUZENT_PORT`, then the default `25314`, then the older `8000`

Everything but the override has to answer `/system/version` to be chosen. The
result sets both the client's API base and the Vite proxy targets, and is printed
at startup:

```text
  suzent backend  http://127.0.0.1:25314  (runtime/service.json, answering)
```

Requests then arrive from the Vite origin, which the backend's CORS policy
already allows as loopback. The search runs once, at startup, so a backend you
start afterwards needs a Vite restart -- or name it directly:

```bash
VITE_SUZENT_BACKEND=http://127.0.0.1:9000 npm run dev
```

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
