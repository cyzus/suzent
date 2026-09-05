---
title: Browser
---

Suzent supports a managed Playwright browser through `browser_action`. To use
existing Chrome or Edge tabs and their signed-in sessions, connect the Playwright
MCP extension separately through Suzent's MCP settings.

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
point it at your everyday browser's user-data directory: use the extension below
for that. A dedicated profile starts with no everyday browser logins, and only
one browser process can use a profile at a time.

### Commands and snapshots

Arguments are strings in a list. Malformed commands fail before browser startup.

| Command | Arguments |
| --- | --- |
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

The native preview and browser tool still share one managed page across chats.
Operations are serialized, but this is not per-chat browser isolation. Coordinate
manual interaction with the agent. Popups, frame traversal, shadow-DOM observation,
download management, and tab selection are not yet exposed by the native tool.
Persistence and using an installed browser do not guarantee avoiding site challenges.

## Existing Chrome or Edge sessions

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
continues to control the managed browser. The native Suzent preview does not display
the extension's tabs. Disconnect through the extension when finished.

This is a setup recipe using the existing MCP adapter, not an automatic extension
installation or a completed native UI integration. For a remote/container backend,
the extension bridge must run on your computer and needs a separately configured,
authenticated connection; a browser launched on the server is not your local browser.
After validating a Playwright MCP version for your environment, pin that version
instead of `@latest` for repeatable deployments.
