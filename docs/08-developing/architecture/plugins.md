---
sidebar_position: 11
title: Plugins
---

# Plugins

This page is for plugin authors and contributors. For installing and enabling
plugins, see [Plugins](../../03-features/plugins.md).

A plugin is Python code that registers tools, slash commands and skills
through one function, `register(ctx)`. It is the in-process counterpart to MCP:
reach for MCP when a tool should work with any agent or needs process
isolation, and for a plugin when it should use Suzent's own tool pipeline
(approvals, output caps, ToolSearch), add slash commands, or ship skills.

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
uv run suzent plugin enable dice
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

1. Packages exposing an entry point in the `suzent.plugins` group. The entry
   point's name is the plugin id; its target is `register` or a module defining
   it. Version and description come from the package metadata.
2. `<data dir>/plugins/<id>/`.
3. Each directory in `SUZENT_PLUGINS_DIR` (`os.pathsep`-separated).

A later source with the same id replaces an earlier one, so a checkout under
`SUZENT_PLUGINS_DIR` overrides an installed copy.

Discovery reads only manifests and package metadata. A plugin's code is
imported only when its id is in `<data dir>/config/plugins.json`
(`{"enabled": [...]}`), which `suzent plugin enable|disable` edits. Loading is
lazy and happens once per process, the first time the tool registry, the skill
manager or the slash-command registry is used. A plugin whose `api_version` is
newer than the running Suzent supports is refused.

A pip-packaged plugin declares itself in its `pyproject.toml`:

```toml
[project.entry-points."suzent.plugins"]
dice = "suzent_dice:register"
```

## Security model

Plugins run in the Suzent process with the user's permissions. Being disabled
by default is the consent step; there is no sandbox and no capability system
around plugin code. Tools a plugin adds are still subject to the user's tool
approval policy, the same as built-in tools.
