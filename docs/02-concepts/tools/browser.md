---
title: Browser
---

Suzent's native `browser_action` tool can launch a managed browser or connect
to your running Chrome or Edge, including its signed-in sessions. MCP is optional.

## Managed browser

The default remains an isolated headless Chromium session. In the desktop app,
open **Settings → Browser** to choose Chromium, Chrome, or Edge, enable
**Remember browser logins**, and turn on **Show browser window**. Changes save
automatically and apply on the next browser tool action or navigation from the
native preview. The backend keeps running. If settings changed, Suzent waits for
the current managed-browser action to finish, then relaunches only that browser.
The current page is reset and temporary sessions lose their login state; logins
already saved in a persistent profile remain there. Start with `open` or `snapshot`
after a settings change; interactions using the previous page are rejected.

Chrome and Edge are detected in the standard installation locations supported by
Playwright on the backend computer. Missing browsers are disabled in the picker.
Use **Check installed browsers** after installing or removing a browser. Chromium
remains selectable and is downloaded on first use if needed. Detection checks for
browser files; it does not launch them or verify system dependencies. Nonstandard
portable installations are not detected. A saved selection is never silently changed.

Settings are stored in `config/browser.json` inside `SUZENT_DATA_DIR`. Environment
variables take precedence; overridden controls are disabled in the desktop app.
For CLI deployments, set these variables before starting the backend from the same
PowerShell terminal:

```powershell
$env:SUZENT_BROWSER_PERSISTENT = "true"
$env:SUZENT_BROWSER_HEADLESS = "false"
$env:SUZENT_BROWSER_CHANNEL = "msedge"
uv run suzent serve
```

Use `chrome` for installed Google Chrome, `msedge` for installed Microsoft Edge,
or `chromium` (the default) for Playwright's bundled browser. Install bundled
Chromium with `uv run playwright install chromium` if needed. Visible mode lets
you sign in or complete a verification step directly in the managed browser.

The profile defaults to `browser_profile` inside `SUZENT_DATA_DIR` (normally
`~/.suzent/browser_profile`). `SUZENT_BROWSER_PROFILE_DIR` can select a different
dedicated directory. Environment variables must be set in the backend process;
desktop settings can be changed while it is running. Do not
point it at your everyday browser's user-data directory: use existing-browser mode below
for that. A dedicated profile starts with no everyday browser logins, and only
one browser process can use a profile at a time.

### Commands and snapshots

Arguments are strings in a list. Malformed commands fail before browser startup.

| Command | Arguments |
| --- | --- |
| `tabs` | `[]` lists open tabs with stable IDs |
| `select_tab` | `["tab-1"]` selects an ID returned by `tabs`; take a fresh snapshot |
| `open` | `[url]`, or `[]` for `about:blank`; HTTP(S) only |
| `snapshot` | `[]`, `[offset, limit]` (limit 1–100), or `["-i"]` for controls only |
| `click`, `dblclick`, `hover` | `[ref]` |
| `fill`, `type` | `[ref, text]`; explicitly pass `""` to clear a field |
| `press` | `[ref, key]`, such as `["@g3e0", "Enter"]` |
| `click_coords` | `[x, y]`, non-negative integers |
| `scroll` | `[dx, dy]`, or `[]` to scroll down 500 pixels |
| `back`, `forward`, `reload`, `refresh` | `[]` |

Snapshots include URL, title, document readiness, a snapshot ID, up to 80 controls
by default, and up to 4,000 characters of page text. They identify omitted controls
with the next offset. For example, `["80", "80"]` requests the next range. Input
values and editable drafts are omitted; fill/type results do not echo entered text.
This is not a general redactor for sensitive text rendered elsewhere on a page.

Use exact refs from the latest snapshot, such as `@g3e0`. A new snapshot or navigation
expires previous refs. Detached nodes and changes to observed element identity
are rejected instead of resolving the ref to another DOM element. CSS selectors
are no longer accepted as refs. Take a fresh snapshot after manual interaction.

Document readiness does not guarantee application hydration. If a page is empty,
inspect the returned metadata and observe again; do not blindly repeat actions.
Actions have a five-second timeout and navigation a fifteen-second timeout.
Dialogs retain Playwright's default automatic dismissal.

### Current boundaries

The native preview and browser tool still share one selected page across chats.
Operations are serialized, but this is not per-chat browser isolation. Coordinate
manual interaction with the agent. Popups, frame traversal, shadow-DOM observation,
and download management are not yet exposed by the native tool.
Persistence and using an installed browser do not guarantee avoiding site challenges.

## Use your browser with the Suzent extension

The recommended personal-browser mode is **Settings → Browser → Use my browser
(extension)**. It uses the tabs and logins in the browser profile where you install
the extension, without MCP or remote-debugging settings.

1. Use the local extension folder shown in Settings (`extensions/browser/` in your
   Suzent checkout). Alternatively, click **Download extension** and extract the ZIP
   into a permanent folder.
2. In Chrome or Edge, open Extensions → Manage extensions. Enable Developer mode,
   choose **Load unpacked**, and select that folder containing `manifest.json`.
3. Back in Suzent, click **Pair browser**. The default browser opens a local pairing
   page. If you installed the extension in another browser, copy the private pairing
   link displayed in Suzent into that browser instead.
4. Settings automatically shows **Browser extension connected**. Ask the agent to
   list your tabs and select one, or open a new page. The native preview follows the
   selected tab.

Installation and pairing are one-time steps per profile. Pairing links expire after
five minutes. Pairing also registers a per-user native messaging helper that reads only Suzent’s
runtime port file. The extension uses it to find the backend again after browser
or backend restarts, including desktop port changes. If system policy blocks
helper registration, the last paired address remains usable; pair again if that
address changes. The helper remains installed after disconnect but cannot grant
browser access without a valid pairing token. Only one browser
profile is paired at a time; pairing another replaces the previous authorization.

**Disconnect and forget** revokes the pairing. Disconnect in the extension popup
also removes its saved credentials. Canceling Chrome/Edge's debugger banner stops
the connection and clears the extension's saved pairing, so the agent cannot
immediately resume control. Browser tabs remain open. Switching back to managed
mode detaches from the selected tab but retains pairing for later use.

This PR provides an unpacked extension; there is no store listing yet. Browser
extension installation and browser permission prompts cannot be skipped. Store
publication can simplify installation later. Enterprise policies may prohibit
unpacked extensions or debugger access.

The extension only operates on HTTP(S) pages and blank tabs, excludes private tabs,
and attaches its debugger only to the selected tab. Its pair token authorizes the
local Suzent backend to control web tabs in that profile. Pairing uses a loopback
connection, a five-minute random token, extension-origin binding, and a persisted
token hash on the backend. The token itself stays in extension local storage.
There is no public debugging port. Page content cannot access the isolated-world
snapshot references. Browser navigation, tab changes, and reconnects expire refs;
commands are not automatically replayed after transport failure.

Snapshots remain bounded and omit form values. Extension interactions validate
observed node identity and wait briefly for visibility and hit testing; they do not
provide every Playwright auto-wait guarantee. Embedded frames, file uploads,
download management, select-option filling, and complex keyboard layouts are not
part of this extension version. Coordinate control requires a fresh visual preview;
manual browser activity can change the page at any time.

### Extension development

Browser-side source lives in `extensions/browser/`. The current installer clones
the repository, so no separate extension packaging or build step is required.
The optional download endpoint creates a ZIP from that directory. A standalone
Python wheel alone does not include the extension source. Python browser code lives
in `src/suzent/tools/browser/`, with the extension bridge in its `extension/` package.
No Node runtime is required for users. Load the source directory unpacked for development,
then reload the extension after changes. English and Chinese extension strings are
in `_locales/`. Run `uv run pytest tests/tools/test_browser_extension.py` for the
real bundled-Chromium extension regression, using an isolated test profile.

## Direct connection to existing Chrome or Edge (advanced)

An already-open browser does not automatically expose a debugging endpoint.
If Suzent reports a missing local debugging endpoint, the saved connection mode is
**Direct connection (advanced)** (`existing`). To use the extension instead, select
**Use my browser (extension)** and complete installation and pairing above. Changing
this preference applies to the next browser action without restarting the backend.

1. Run the Suzent backend on the same computer as your browser.
2. In Chrome, open `chrome://inspect/#remote-debugging`; in Edge, open
   `edge://inspect` and choose **Remote debugging**. Enable remote debugging.
3. In **Settings → Browser**, select **Direct connection (advanced)**, then
   choose Chrome or Edge. Approve the browser's connection prompt when it appears.
4. Ask the agent to list tabs (`tabs`), select one (`select_tab ["tab-1"]`),
   and take a snapshot before interacting.

Suzent discovers the local endpoint from `DevToolsActivePort` in the selected
browser's standard stable-channel user-data directory. It does not launch a
second process with your profile or copy cookies. No debugging endpoint means
an actionable error; there is no fallback to launching a managed browser.
Custom user-data paths, other channels, and remote computers are not supported.
Browser installation detection does not verify that remote debugging is enabled.

Attachment starts on a new blank tab to avoid navigating away from personal work.
The native preview follows the selected tab. Your existing browser and all its tabs
remain open when Suzent shuts down or switches modes. If a tab closes or the
connection drops, Suzent reconnects on the next action; it rejects that action if
it could replay an interaction against a different page. List tabs or take a new
snapshot to continue. Tab IDs expire when the connection is replaced.

The browser's own consent prompt and automation banner remain in place. The agent
can access signed-in sessions through this connection. Managed-profile and
headless settings have no effect in this mode. Playwright's CDP connection has
lower compatibility than its managed connection, and may apply browser-context
defaults (for example download handling); advanced behavior needs browser-specific
validation. See [Playwright CDP documentation](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect-over-cdp)
and [Microsoft's existing Edge connection guide](https://learn.microsoft.com/en-us/microsoft-edge/web-platform/devtools-mcp-server).

For CLI configuration, set `SUZENT_BROWSER_CONNECTION_MODE=existing` and
`SUZENT_BROWSER_CHANNEL=chrome` or `msedge` before starting the backend.

## Optional MCP extension

Microsoft's [Playwright extension](https://github.com/microsoft/playwright/tree/main/packages/extension)
connects to selected tabs in your existing browser, including their logged-in state.
Use it through Suzent's existing MCP integration:

1. Install the Playwright extension using the official instructions above.
2. Ensure Node.js/npm are available on the computer running the Suzent backend.
3. With the backend running on the same computer as your browser, register the server:

```powershell
uv run suzent mcp add personal-browser --command npx --args "-y,@playwright/mcp@latest,--extension"
uv run suzent mcp test personal-browser
```

On the first browser action, approve the extension connection and select the tab
to share. Use the `personal-browser` MCP tools for those tabs; `browser_action`
controls the browser selected in Settings. The native Suzent preview does not display
the extension's tabs. Disconnect through the extension when finished.

This is a setup recipe using the existing MCP adapter, not an automatic extension
installation or a completed native UI integration. For a remote/container backend,
the extension bridge must run on your computer and needs a separately configured,
authenticated connection; a browser launched on the server is not your local browser.
After validating a Playwright MCP version for your environment, pin that version
instead of `@latest` for repeatable deployments.
