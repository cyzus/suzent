---
sidebar_position: 10
title: Plugins
description: Add tools, slash commands and skills to Suzent with plugins you install and switch on yourself.
---

# Plugins

A plugin adds things to Suzent that a skill or an MCP server can't: new tools
that run inside Suzent with its approvals and limits, new slash commands that
work in the app and in chat apps, and skills that come bundled with them.

**Off until you say so.** A plugin's code runs inside Suzent with your
permissions, so nothing a plugin ships runs until you enable it. Only enable
plugins you trust, the same as any program you install.

## Install a plugin

Put the plugin's folder (the one holding `plugin.yaml`) in the `plugins` folder
inside Suzent's data folder:

| System | Plugins folder |
|---|---|
| macOS | `~/Library/Application Support/com.suzent.app/plugins` |
| Windows | `%LOCALAPPDATA%\com.suzent.app\plugins` |
| Linux | `~/.local/share/com.suzent.app/plugins` |

Plugins published as Python packages work too: install the package into the
same environment as Suzent and it shows up in the list.

## Turn a plugin on or off

```bash
suzent plugin list             # what's installed, and whether it's on
suzent plugin enable dice      # turn one on
suzent plugin disable dice     # turn it off
```

Restart Suzent after enabling or disabling a plugin.

Once a plugin is on:

- **Tools** it adds are available to the agent. Tools the plugin puts in a tool
  group appear in the tool picker; the rest the agent finds by searching when it
  needs them.
- **Slash commands** it adds work wherever slash commands do. Type `/help` to see them.
- **Skills** it adds appear on the Skills page under **Plugin**, already enabled.

If a plugin fails to load, Suzent keeps running without it, and
`suzent plugin list` shows the error.

## Writing your own

See [Plugins](../08-developing/architecture/plugins.md) in the developer docs,
and the example plugin in `examples/plugins/dice` in the repository.
