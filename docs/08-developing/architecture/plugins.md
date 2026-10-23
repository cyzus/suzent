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
  `pyproject.toml` (`social` names the `social` extra, which holds the chat app
  SDKs). A third-party plugin lists pip requirements instead.
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
| `aliases` | Other names `suzent plugin install` and the API accept, e.g. `telegram` for `social`. |
| `extras` | Extras of Suzent's own package this plugin needs. Only meaningful for built-in plugins. |
| `dependencies` | pip requirements of a third-party plugin. |
| `default_enabled` | On until the user removes it. Honoured only for built-in plugins. |

A plugin with no `__init__.py` only brings packages; `plugins/social/` is one.

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

## `PluginContext`

| Method | What it does |
|---|---|
| `register_tool(tool_cls)` | Adds a `suzent.tools.base.Tool` subclass. It goes through the same `_make_tool()` wrapper as built-in tools, so `requires_approval`, `output_char_limit`, the user's approval policy and ToolSearch deferral all apply. Without a `group` it is not in the tool picker and is reached through ToolSearch; with one it is listed under that capability. |
| `register_skills(path)` | Adds a directory of skill folders. Relative paths resolve against the plugin directory. Skills get source `plugin` and id `plugin:<plugin-id>:<skill-name>`, are enabled by default, and are mounted read-only into the sandbox under `/mnt/skills/plugins/`. |
| `register_command(aliases, **options)` | Decorator with the same signature and handler contract as `suzent.core.commands.base.register_command`. |
| `id`, `manifest`, `path`, `logger` | The plugin's id, parsed manifest, directory (`None` for pip packages) and a logger bound to `suzent.plugins.<id>`. |

Registrations are buffered on the context and committed only after `register()`
returns. If it raises, the plugin is marked `error` and nothing it registered
reaches the live registries.

Name clashes never replace existing behaviour: a tool whose `name` or
`tool_name` is already taken, or a command with an alias already registered, is
skipped with a warning.

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
    "social": {"enabled": true, "requested_by": ["telegram"]},
    "dice": {"enabled": false, "requested_by": []}
  }
}
```

A plugin with no entry is on only if it is built-in and `default_enabled`; an
explicit `false` is kept, so a removed default stays removed. `requested_by`
records the names the user installed it under.

A plugin's code is imported only when it is enabled. Loading is lazy and
happens once per process, the first time the tool registry, the skill manager
or the slash-command registry is used. A plugin whose `api_version` is newer
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

`missing_packages()` compares what a plugin declares with what is installed,
for `suzent plugin status` and the settings page.

## Settings page and API

| Route | What it does |
|---|---|
| `GET /plugins` | Every plugin with `enabled`, `status`, `missing` packages and `restartRequired`. |
| `POST /plugins/{name}/install` | Enables a plugin by id or alias, installs its packages, and, when it brought packages, rebuilds the social stack with `reload_social()` so a chat app whose SDK just arrived connects without a restart. A failed install returns `502` with uv's output; the plugin stays enabled so a retry reinstalls. |
| `POST /plugins/{name}/remove` | Disables a plugin, and for one that brought packages, rebuilds the social stack so its chat apps stop. |

`ChannelManager` skips a configured chat app whose providing plugin (matched
by id or alias, e.g. `telegram` → `social`) is removed. Chat apps no plugin
claims, such as WeChat, always load.

Packages take effect immediately. Tools, commands and skills are registered
once per process, so a plugin with code reports `restartRequired` until the
backend restarts.

## Security model

Plugins run in the Suzent process with the user's permissions. Only built-in
plugins can turn themselves on; any other plugin stays off until the user
installs it, which is the consent step, and the settings page asks for
confirmation before installing third-party code. There is no sandbox and no
capability system around plugin code. The API only accepts names of
discovered plugins, never package names. Tools a plugin adds are still subject to the user's tool
approval policy, the same as built-in tools.
