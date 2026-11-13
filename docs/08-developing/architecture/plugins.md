---
sidebar_position: 11
title: Plugins
---

# Plugins

This page is for plugin authors and contributors. For installing and enabling
plugins, see [Plugins](../../03-features/plugins.md).

A plugin is a unit the user installs and removes. It can bring packages, code,
or both:

- **Packages.** A built-in plugin names extras from Suzent's own
  `pyproject.toml`: each chat app has its own extra and plugin (`telegram`,
  `slack`, `discord`, `feishu`), and the `social` extra still pulls in all four
  for scripted installs. A third-party plugin lists pip requirements instead.
- **Code.** An `__init__.py` with `register(ctx)` adds tools, slash commands and
  skills.

For code, a plugin is the in-process counterpart to MCP: reach for MCP when a
tool should work with any agent or needs process isolation, and for a plugin
when it should use Suzent's own tool pipeline (approvals, output caps,
ToolSearch), add slash commands, or ship skills.

## Layout

```
dice/
├── plugin.yaml
├── __init__.py        # defines register(ctx)
└── skills/
    └── dice-games/SKILL.md
```

`plugin.yaml`:

```yaml
id: dice               # lowercase letters, digits, - and _; unique
name: Dice
version: 0.1.0
description: Adds a dice tool, a /roll command and a skill.
api_version: 1         # plugin API this plugin was written against
```

| Field | Meaning |
|---|---|
| `aliases` | Other names `suzent plugin install` and the API accept, e.g. `lark` for `feishu`. |
| `channel` | The chat app this plugin provides, as keyed in `config/social.json`. See [Chat-app plugins](#chat-app-plugins). |
| `extras` | Extras of Suzent's own package this plugin needs. Only meaningful for built-in plugins. |
| `dependencies` | pip requirements of a third-party plugin. |
| `default_enabled` | On until the user removes it. Honoured only for built-in plugins. |
| `icon` | An SVG or PNG file in the plugin folder (under 64 KB), shown on the plugins page. Built-in service logos come from [Simple Icons](https://simpleicons.org) (CC0). |
| `category` | `service` lists the plugin under **Settings → Services** instead of **Plugins**. Chat-app plugins (those with `channel`) are left off the Plugins page, because Social Channels installs them. |
| `binaries` | Programs the plugin runs on the host, downloaded after the user agrees. See [Binaries](#binaries). Needs `api_version: 3`. |

A plugin with no `__init__.py` only brings packages; `plugins/telegram/` is one.

`__init__.py`:

```python
from suzent.plugins import PluginContext
from suzent.tools.base import Tool, ToolResult


class RollDiceTool(Tool):
    name = "RollDiceTool"          # registry key, unique across all tools
    tool_name = "roll_dice"        # name the model calls
    description = "Roll dice and return each result and the total."

    def forward(self, count: int = 1, sides: int = 6) -> ToolResult:
        ...


def register(ctx: PluginContext) -> None:
    ctx.register_tool(RollDiceTool)
    ctx.register_skills("skills")

    @ctx.register_command(["/roll"], description="Roll dice")
    def roll(count: int = 1):
        async def _impl() -> str:
            return "..."
        return _impl
```

The full, runnable version is `examples/plugins/dice`. Try it from a checkout:

```bash
export SUZENT_PLUGINS_DIR=examples/plugins
uv run suzent plugin install dice
uv run suzent start
```

`plugins/desktop` is the optional desktop computer-use plugin shipped with
Suzent. It is built in and `default_enabled: false`. All of its code lives
in the plugin folder: `register()` adds `DesktopTool` and the
`suzent-desktop` skill, and hands `runner` the `agent-desktop` binary its
manifest declares. The tool execs that binary on the host; it never enters
the per-chat Docker sandbox. It is the reference for both [Binaries](#binaries)
and [Classifying tool calls](#classifying-tool-calls). See
[Desktop apps](../../03-features/tools/desktop.md).

`plugins/wake-word` brings the `wake` extra (sherpa-onnx, pypinyin) and the
keyword spotter that uses it. `register()` serves `GET status` and
`POST model` with `register_route` and the `listen` socket with
`register_websocket`, so all three go away when the plugin is off. The voice
settings it reads (`wake_word`, `wake_phrases`, `wake_sensitivity`) stay in
core. It is the reference for `register_websocket`.

## `PluginContext`

| Method | What it does |
|---|---|
| `register_tool(tool_cls)` | Adds a `suzent.tools.base.Tool` subclass. It goes through the same `_make_tool()` wrapper as built-in tools, so `requires_approval`, `output_char_limit`, the user's approval policy and ToolSearch deferral all apply. Without a `group` it is not in the tool picker and is reached through ToolSearch; with one it is listed under that capability. |
| `register_skills(path)` | Adds a directory of skill folders. Relative paths resolve against the plugin directory. Skills get source `plugin` and id `plugin:<plugin-id>:<skill-name>`, are enabled by default, and are mounted read-only into the sandbox under `/mnt/skills/plugins/`. |
| `register_integration(integration)` | Connects the agent to a hosted service through its MCP server, once the user signs in. See [Integrations](#integrations). Needs `api_version: 2`. |
| `binary(name)` | A `PluginBinary` handle on a program declared under `binaries`. Its `locate()` returns `(path, source)` or `None` and never downloads. See [Binaries](#binaries). |
| `register_route(path, endpoint, methods=("GET",))` | Serves a Starlette endpoint at `/plugins/<id>/api/<path>` while the plugin is loaded, for a settings page that needs more than the generic plugin card. See [Settings page and API](#settings-page-and-api). |
| `register_websocket(path, endpoint)` | Serves a Starlette WebSocket endpoint at `/plugins/<id>/ws/<path>` while the plugin is loaded. Remote callers need a full-access device token, and the Origin is checked before the endpoint runs. See [Settings page and API](#settings-page-and-api). Needs `api_version: 4`. |
| `secrets` | A `PluginSecrets` with `get`, `set` and `delete`, namespaced to the plugin. Values are stored as `SUZENT_PLUGIN::<id>::<name>`, a private prefix that `inject_all_to_env` skips, so the agent's shell commands never inherit them. |
| `register_command(aliases, **options)` | Decorator with the same signature and handler contract as `suzent.core.commands.base.register_command`. |
| `id`, `manifest`, `path`, `logger` | The plugin's id, parsed manifest, directory (`None` for pip packages) and a logger bound to `suzent.plugins.<id>`. |

Registrations are buffered on the context and committed only after `register()`
returns. If it raises, the plugin is marked `error` and nothing it registered
reaches the live registries.

Name clashes never replace existing behaviour: a tool whose `name` or
`tool_name` is already taken, or a command with an alias already registered, is
skipped with a warning.

## Integrations

An `Integration` (`suzent.plugins.Integration`) describes one hosted service:

```python
from suzent.plugins import Integration


def _toolset(client):
    from pydantic_ai_harness.notion import Notion

    return Notion(client=client).get_toolset()


def register(ctx):
    ctx.register_integration(
        Integration(
            id="notion",
            name="Notion",
            url="https://mcp.notion.com/mcp",
            auth="oauth",       # or "token" for a token the user pastes
            build=_toolset,
        )
    )
```

`plugins/notion`, `plugins/linear` and `plugins/github` use the hosted-MCP
capabilities from `pydantic-ai-harness`. `plugins/cloudflare` and
`plugins/stripe` have no harness capability, so `build` wraps the client in a
plain `MCPToolset`, prefixed because their servers use generic tool names such
as `execute`.

- **`auth="oauth"`**: `build` gets a FastMCP `Client` that adds the user's
  access token and refreshes it. `core/mcp_oauth.py` runs the sign-in with
  FastMCP's `OAuth`: discovery, dynamic client registration and PKCE. The
  redirect goes to a loopback port on the machine running Suzent. The
  settings page opens the authorization URL itself, so the server never opens
  a browser. Tokens and the client registration are stored through
  `core/secrets.py` (`SecretKeyValueStore`), one entry each under
  `SUZENT_MCP_OAUTH::<plugin>.<id>::`. A new sign-in clears them and
  registers again, because the loopback port changes. During a run the
  provider refreshes tokens but never starts a sign-in: without a usable
  token it raises `SignInRequired`.
- **`auth="token"`**: `build` gets the token string, stored as
  `SUZENT_MCP_TOKEN::<plugin>.<id>`. GitHub uses this because it does not
  allow dynamic client registration.

Both prefixes are in `secrets.PRIVATE_KEY_PREFIXES`, so
`inject_all_to_env()` never copies them into the environment, where commands
the agent runs would inherit them.

`agent_manager._build_mcp_servers()` adds `integrations.connected_toolsets()`,
which has one toolset for each connected, switched-on integration of each
loaded plugin. The switch lives in `plugins.json` as
`plugins[id].services[integration_id]`: `connect` writes `false` when there is
no entry yet, and an integration with no entry (connected before the switch
existed) counts as on. A chat's `mcp_enabled["plugin.integration"]` overrides
it. Each toolset is wrapped twice:

- `_as_mcp_toolset()` counts it as MCP for context usage and sends every call
  the server does not mark `readOnlyHint` through the permission engine,
  exactly like user-added MCP servers.
- A tolerant wrapper turns a failed connection (expired sign-in, service
  down) into no tools for that run. Without it, the failure would break every
  chat. The error is shown on the plugins page.

Routes: `POST /plugins/{name}/integrations/{id}/connect` starts a sign-in and
returns `authorizeUrl`, or saves `{"token": ...}`.
`POST /plugins/{name}/integrations/{id}/disconnect` signs out.
`POST /plugins/{name}/integrations/{id}/enabled` with `{"enabled": bool}` sets
the switch. All three rebuild the cached agent. `GET /plugins` lists each
plugin's `integrations` with `connected`, `enabled`, `error`, and a `signIn`
state while one is in progress.

Signing in from a phone is not supported yet: the OAuth redirect must reach
the loopback callback on the Suzent machine.

## Binaries

A plugin that drives a command-line program declares it in `plugin.yaml`
instead of downloading it itself. `suzent.plugins.binaries` does the rest.

```yaml
api_version: 3
binaries:
  - name: agent-desktop
    version: 1.2.0
    package: agent-desktop           # npm package carrying the builds
    sha256: 9e4b1a69...              # of the npm tarball
    env: SUZENT_AGENT_DESKTOP_BIN    # optional override the user can set
    platforms:                       # npm platform names
      darwin-arm64:
        files:                       # installed name: path in the tarball
          agent-desktop: bin/agent-desktop-darwin-arm64       # first = executable
          agent-desktop-macos-helper: bin/agent-desktop-macos-helper-darwin-arm64
      win32-x64:
        files:
          agent-desktop.exe: bin/agent-desktop-win32-x64.exe
    after_install:
      darwin: [permissions, --guide]  # run once, per OS
    notice: Shown with the consent prompt.
```

- **Source.** The artifact is always an npm tarball, so it reaches users who
  cannot reach GitHub: `tarball_urls()` tries `registry.npmmirror.com` first
  when `network_region.china_mode()` is on and `registry.npmjs.org` first
  otherwise, falling back to the other on a download error. npmmirror copies
  public npm packages without review, so publishing to npm is enough. When
  each platform is its own package (for example `@suzent/himalaya-linux-x64`),
  a platform entry sets its own `package` and `sha256`.
- **Verification.** The tarball's SHA-256 must equal the manifest's. A
  mismatch stops the install rather than trying the next registry. Only the
  members listed for the current platform are extracted, as regular files,
  into `<data dir>/plugin-bin/<plugin>/<name>/<version>/`, marked executable,
  with an `install.json` recording what was installed. The directory is built
  under a `.partial` name and renamed into place.
- **Lookup.** `locate()` uses the `env` override when set (and returns `None`
  if it is not executable, rather than silently using something else), then
  Suzent's copy, then `command` (default `name`) on `PATH`.
- **Consent.** Only `POST /plugins/{name}/binaries/{binary}/install` with
  `{"confirmed": true}` and `suzent plugin install` (after a prompt, or
  `--yes`) download. Tools only call `locate()`. `GET /plugins` reports each
  binary's status under `binaries`, and the plugin card shows an install
  button with the consent text.
- **Updates.** The weekly `check-plugin-binaries` workflow runs
  `scripts/check_plugin_binaries.py`. It takes a newer stable release only
  when it is at least seven days old, and, on npm, from the same trusted
  publisher with provenance. It rewrites `version` and `sha256` in the
  manifest and opens a pull request for review. For himalaya it follows the
  upstream GitHub release and updates `scripts/pack_himalaya_npm.py`; merging
  that publishes the npm packages, and a later run moves the email plugin's
  pin. New commands in a release still have to be added to the plugin by
  hand.

## Classifying tool calls

A tool with `requires_approval` can tell the permission engine more about
each call by overriding three classmethods on `suzent.tools.base.Tool`. They
receive the raw arguments, so they must validate rather than trust them.

| Method | Effect |
|---|---|
| `is_readonly_call(args) -> bool` | True lets the call run without asking, and in strict read-only and plan modes. |
| `invalid_call_reason(args) -> str \| None` | A reason refuses the call before approval (`reason_code` `invalid_tool_call`), so a call that can never run is not offered for approval. |
| `remember_as(args) -> RememberAs \| None` | What "always allow" stores. `RememberAs({"command": "click"}, "desktop click")` stores an `exact_input` rule for those arguments; `RememberAs(None)` offers only a one-time allow; `None` (the default) trusts the whole tool. |

The engine finds the class with `registry.get_tool_class()`, so the hooks
work for plugin tools without any change to `suzent.permissions`.

## Discovery and loading

`suzent.plugins.manager.PluginManager` finds plugins in, from lowest to highest
precedence:

1. `<repo>/plugins/<id>/`, the built-in plugins shipped with Suzent.
2. Packages exposing an entry point in the `suzent.plugins` group. The entry
   point's name is the plugin id; its target is `register` or a module defining
   it. Version and description come from the package metadata.
3. `<data dir>/plugins/<id>/`.
4. Each directory in `SUZENT_PLUGINS_DIR` (`os.pathsep`-separated).

A later source with the same id replaces an earlier one, so a checkout under
`SUZENT_PLUGINS_DIR` overrides an installed copy.

Discovery reads only manifests and package metadata. The user's choices live in
`<data dir>/config/plugins.json`:

```json
{
  "version": 1,
  "plugins": {
    "feishu": {"enabled": true, "requested_by": ["lark"]},
    "dice": {"enabled": false, "requested_by": []}
  }
}
```

A plugin with no entry is on only if it is built-in and either `default_enabled`
or a chat-app plugin whose app is set up; an explicit `false` is kept, so a
removed default stays removed. `requested_by` records the names the user
installed it under.

A plugin's code is imported only when it is enabled. The initial load is lazy,
the first time the tool registry, the skill manager or the slash-command
registry is used. After that, `activate()` and `deactivate()` load and unload
single plugins in the running process (see [Hot loading](#hot-loading)). A plugin whose `api_version` is newer
than the running Suzent supports is refused.

A pip-packaged plugin declares itself in its `pyproject.toml`:

```toml
[project.entry-points."suzent.plugins"]
dice = "suzent_dice:register"
```

## Dependencies

`suzent.plugins.deps` installs what a plugin needs. Installing never removes
anything, so it is safe while the backend runs from the same environment.

- **Extras** go into Suzent's environment with
  `uv sync --frozen --inexact --extra <every enabled plugin's extras>`, run in
  the project directory. `--inexact` adds missing packages and leaves the rest.
  A Suzent that was installed with pip rather than from a checkout has no
  `uv.lock`, so the install fails with the `pip install 'suzent[...]'` to run
  instead.
- **Third-party `dependencies`** go into `<data dir>/plugins/.deps/<id>/` with
  `uv pip install --target` (or `pip` when uv is missing), and that directory is
  added to `sys.path` when the plugin loads. Keeping them out of the
  environment means the exact `uv sync` an upgrade runs cannot remove them.

`suzent upgrade` builds its sync from the same state: `_backend_sync_args()`
passes `--extra` for each extra an enabled plugin needs, plus `dev` in a
development checkout. That sync is exact, so packages of plugins the user
removed are cleaned up then. A checkout older than plugins (no `plugins/`
folder, for instance after a rollback) gets `--extra social`, as before.
`_plugin_extras()` reads `config/social.json` from the checkout too, so a chat
app that is set up but has no state entry keeps its packages.

The desktop installer and updater (`apps/suzent-installer`) and the setup
scripts sync the same set. They cannot import Suzent before its environment
is synced, so the rules live in `suzent/plugins/enablement.py`, which imports
nothing from Suzent: they run it by path on the environment's Python
(`enablement.py <checkout> <plugins.json>` prints the extras as JSON), and
`PluginManager` uses the same functions. A fresh install syncs no plugin
extras; when the script is missing or fails, they fall back to `social`.

`missing_packages()` compares what a plugin declares with what is installed,
for `suzent plugin status` and the settings page.

## Settings page and API

| Route | What it does |
|---|---|
| `GET /plugins` | Every plugin with `enabled`, `status`, `missing` packages and `restartRequired`. |
| `POST /plugins/{name}/install` | Enables a plugin by id or alias, installs its packages, `activate()`s it, and, when it brought packages, rebuilds the social stack with `reload_social()` so a chat app whose SDK just arrived connects. A failed install returns `502` with uv's output; the plugin stays enabled so a retry reinstalls. |
| `POST /plugins/{name}/remove` | Disables and `deactivate()`s a plugin, and for one that brought packages, rebuilds the social stack so its chat app stops. |
| `POST /plugins/{name}/binaries/{binary}/install` | Downloads a declared binary. Refuses with `400` unless the body is `{"confirmed": true}`; a failed download or checksum returns `502`. |
| `/plugins/{name}/api/{path}` | Dispatches to a route the plugin registered with `register_route`, matched on path and method. `404` while the plugin is not loaded, so turning a plugin off takes its API away with its tools. |
| `WS /plugins/{name}/ws/{path}` | Dispatches to a socket the plugin registered with `register_websocket`. A socket from an origin other than the app's (`voice_origin_allowed`) is refused with `1008`. While the plugin is not loaded, or for a path it did not register, the socket is accepted and closed at once with code `4404`, because a browser cannot see why a handshake was refused. The auth boundary lets only loopback and full-scope tokens through, and accepts the token as a `token` query parameter, since a browser WebSocket cannot set headers. |

`suzent plugin install` and `remove` call these routes when a server answers
(`suzent.client`, `PluginsAPI`), so a change from the terminal applies to the
running process too. With no server they write the state and install packages
themselves, and the next start loads the result.

`restartRequired` is true only when the running process disagrees with the
saved state, which now happens only after an out-of-band change such as a
hand-edited `plugins.json`.

## Chat-app plugins

`plugins/telegram`, `slack`, `discord` and `feishu` are packages-only
plugins with a `channel` field. They have no `default_enabled`; instead a
chat-app plugin with no state entry is on when its section of
`config/social.json` is set up: `enabled` is not false and some value other
than `enabled` and `allowed_users` is non-empty. This is evaluated on every
`discover()`, so users who configured an app before the split keep its
packages on upgrade without a migration step.

The plugin and the app's own switch are kept in step:

- Saving Settings → Social Channels (`save_social_config`) enables the plugin
  of every app that is set up, installs missing packages in a worker thread,
  then calls `reload_social()`.
- `set_enabled()` on a chat-app plugin writes the same value to that app's
  `enabled` in `social.json`, if the app has a section there.

`ChannelManager` asks `for_channel()` and skips a configured app whose plugin
is removed. Apps no plugin claims, such as WeChat, always load.

## Hot loading

`PluginManager.activate(id)` runs a newly enabled plugin's `register()` (or
retries one that failed), and `deactivate(id)` takes a disabled plugin's
commands out of the slash-command registry, drops its deps directory from
`sys.path`, and forgets its module so the next `activate()` runs current code.
Both then refresh what depends on the plugin set:

- the tool registry caches (`reset_tool_caches()`),
- the skill manager singleton (`SkillManager.reset_instance()`),
- the cached agent (`agent_manager.invalidate_agent()`), so the next message
  builds an agent with the new tool list.

Only modules the process already imported are touched, so the CLI never
imports the agent stack. A run already in progress keeps the agent it started
with. Objects a plugin created itself (threads, open connections) are not
torn down; a plugin that starts any should stop them when its module is
garbage collected or provide no such state.

## Security model

Plugins run in the Suzent process with the user's permissions. Only built-in
plugins can turn themselves on; any other plugin stays off until the user
installs it, which is the consent step, and the settings page asks for
confirmation before installing third-party code. There is no sandbox and no
capability system around plugin code. The API only accepts names of
discovered plugins, never package names. Tools a plugin adds are still subject to the user's tool
approval policy, the same as built-in tools. Programs a plugin declares are
downloaded only after the user agrees, and only if their hash matches the
one the plugin ships.
