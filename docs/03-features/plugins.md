---
sidebar_position: 10
title: Plugins
description: Add chat apps, tools, slash commands and skills with plugins, and keep them across upgrades.
---

# Plugins

A plugin adds something to Suzent and brings along whatever it needs to run.
Some plugins only bring packages: each chat app (Telegram, Slack, Discord and
Feishu/Lark) is its own built-in plugin, so you only download the packages for
the apps you use. Others add tools, slash commands and skills of their own.

Suzent remembers which plugins you installed, so an upgrade keeps them, and a
plugin you removed stays removed. Your setup stays yours: nothing is turned on
unless you turn it on.

## Install or remove a plugin

Open **Settings → Plugins** and choose **Install** or **Remove**.

From a terminal, you can use a plugin's name or any of its other names. For
example, `lark` means the Feishu / Lark plugin:

```bash
suzent plugin list               # what's available, and what's on
suzent plugin install telegram   # turn a plugin on and download what it needs
suzent plugin remove slack       # turn it off
suzent plugin status             # anything missing?
suzent plugin sync               # download whatever enabled plugins are missing
```

Changes take effect straight away, with no restart, whether you use Settings
or the terminal. New tools, commands and skills are available from your next
message. Removing a plugin turns it off at once; the packages it downloaded are
cleaned up at the next upgrade. If Suzent isn't running, the terminal commands
save your choice and Suzent loads it the next time it starts.

## Chat apps

Chat-app plugins are off until you use them. Setting up an app under
**Settings → Social Channels** installs its plugin for you, so in most cases
you never need the Plugins page for chat apps. If you already had an app set
up before plugins existed, its plugin is on after the upgrade and keeps
working.

Removing a chat-app plugin also switches that app off under Social Channels.
WeChat needs no extra packages, so it has no plugin and always works.

## Desktop apps

The Desktop plugin lets the agent read and operate native apps on this
computer. It is off until you install it, and it needs the separate
agent-desktop program, which Suzent does not install for you. See
[Desktop apps](./tools/desktop.md).

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
