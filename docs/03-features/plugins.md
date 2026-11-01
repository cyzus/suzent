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

## Notion, Linear and GitHub

These built-in plugins connect the agent to your account on each service, so
it can search and edit Notion pages, read and update Linear issues, or work
with GitHub repositories, issues and pull requests. Each one is off until you
install it and connect your account.

1. Open **Settings → Plugins** and choose **Install** on the service.
2. Connect your account:
   - **Notion and Linear:** choose **Sign in**. A browser window opens on the
     service's own sign-in page. Do this on the computer that runs Suzent.
   - **GitHub:** create a fine-grained personal access token (the **Create a
     token** link opens GitHub's page), paste it and choose **Save**. Give the
     token only the repositories and permissions you want the agent to have.

You stay signed in after a restart. Your sign-in and tokens are kept in your
system keychain. The agent never sees them, and they are not passed to
commands the agent runs.

Anything that changes your data, such as creating a page or commenting on an
issue, asks for your approval first, the same as other tools. Lookups the
service marks as read-only run without asking. Your permission mode and
**Always allow** choices apply as usual.

If a sign-in expires or the service can't be reached, chats keep working
without that service's tools, and the Plugins page shows **Sign in again**.
Choose **Disconnect** to sign out and forget the token.

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
