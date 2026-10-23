---
sidebar_position: 10
title: Plugins
description: Add chat apps, tools, slash commands and skills with plugins, and keep them across upgrades.
---

# Plugins

A plugin adds something to Suzent and brings along whatever it needs to run.
Some plugins only bring packages: the built-in **Chat apps** plugin installs
what Telegram, Slack, Discord and Feishu/Lark need. Others add tools, slash
commands and skills of their own.

Suzent remembers which plugins you installed, so an upgrade keeps them, and a
plugin you removed stays removed.

## Install or remove a plugin

Open **Settings → Plugins** and choose **Install** or **Remove**.

From a terminal, you can use a plugin's name or any of its other names. For
example, `telegram` and `slack` both mean the Chat apps plugin:

```bash
suzent plugin list               # what's available, and what's on
suzent plugin install telegram   # turn a plugin on and download what it needs
suzent plugin remove social      # turn it off
suzent plugin status             # anything missing?
suzent plugin sync               # download whatever enabled plugins are missing
```

**When it takes effect:**

- **Chat apps** start working as soon as the install from Settings finishes. If
  you install from a terminal while Suzent is running, restart Suzent.
- **Plugins that add tools or commands** take effect after you restart Suzent.
- **Removing a plugin** turns it off straight away. The packages it downloaded
  are cleaned up at the next upgrade.

The Chat apps plugin is on by default. WeChat needs no extra packages, so it
works whether this plugin is on or off.

## Plugins from other people

Put the plugin's folder (the one holding `plugin.yaml`) in the `plugins` folder
inside Suzent's data folder, then install it as above:

| System | Plugins folder |
|---|---|
| macOS | `~/Library/Application Support/com.suzent.app/plugins` |
| Windows | `%LOCALAPPDATA%\com.suzent.app\plugins` |
| Linux | `~/.local/share/com.suzent.app/plugins` |

Plugins published as Python packages work too: install the package into the
same environment as Suzent and it shows up in the list.

**Only install plugins you trust.** A plugin that adds tools or commands runs
its code inside Suzent with your permissions. Plugins from other people stay
off until you install them, and Suzent asks you to confirm first.

If a plugin fails to load, Suzent keeps running without it, and the Plugins
page and `suzent plugin list` show the error.

## Writing your own

See [Plugins](../08-developing/architecture/plugins.md) in the developer docs,
and the example plugin in `examples/plugins/dice` in the repository.
