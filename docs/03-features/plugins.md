---
sidebar_position: 10
title: Plugins
description: Add chat apps, tools, slash commands and skills with plugins, and keep them across upgrades.
---

# Plugins

A plugin adds something to Suzent and brings along whatever it needs to run.
Some plugins only bring packages: each chat app (Telegram, Slack, Discord and
Feishu/Lark) is its own built-in plugin, so you only download the packages for
the apps you use. The built-in **Camera** plugin lets the agent take photos
with this computer's webcam; it's off until you install it. Others add tools,
slash commands and skills of their own.

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
**Settings → Social Channels** installs its plugin for you, so chat apps are
not listed on the Plugins page. If you already had an app set
up before plugins existed, its plugin is on after the upgrade and keeps
working.

Removing a chat-app plugin also switches that app off under Social Channels.
WeChat needs no extra packages, so it has no plugin and always works.

## Notion, Linear, GitHub, Cloudflare and Stripe

These built-in plugins connect the agent to your account on each service.
They are listed under **Settings → Services**, not on the Plugins page, and
each one is off until you add it and connect your account.

| Plugin | What the agent can do |
|---|---|
| Notion | Search and edit pages and databases. |
| Linear | Read and update issues, projects and comments. |
| GitHub | Work with repositories, issues and pull requests. |
| Cloudflare | Look up and change anything in the Cloudflare API, such as DNS records, Workers, R2 buckets and analytics, plus search Cloudflare's docs. |
| Stripe | Look up customers, payments, invoices and subscriptions, search Stripe's docs, and make changes such as creating a refund or a payment link. |

1. Open **Settings → Services** and choose **Add** on the service.
2. Connect your account:
   - **Notion, Linear, Cloudflare and Stripe:** choose **Sign in**. A browser window opens on the
     service's own sign-in page. Do this on the computer that runs Suzent.
   - **GitHub:** create a fine-grained personal access token (the **Create a
     token** link opens GitHub's page), paste it and choose **Save**. Give the
     token only the repositories and permissions you want the agent to have.

When you sign in to Cloudflare or Stripe, their own page asks which account
and which permissions to give. With Stripe you can connect a sandbox instead
of your live account while you try it out. Stripe still asks you to confirm
some actions, such as refunds, in its dashboard.

You stay signed in after a restart. Your sign-in and tokens are kept in your
system keychain. The agent never sees them, and they are not passed to
commands the agent runs.

Anything that changes your data, such as creating a page or commenting on an
issue, asks for your approval first, the same as other tools. Lookups the
service marks as read-only run without asking. Your permission mode and
**Always allow** choices apply as usual.

If a sign-in expires or the service can't be reached, chats keep working
without that service's tools, and the Services page shows **Sign in again**.
Choose **Disconnect** to sign out and forget the token.
## Desktop apps

The Desktop plugin lets the agent read and operate native apps on this
computer. It is off until you install it. The agent-desktop program it needs
is downloaded only after you confirm, from its card in Settings or when
`suzent plugin install desktop` asks. See [Desktop apps](./tools/desktop.md).

## Email

The Email plugin lets the agent search and read your mailboxes, save drafts,
and send mail you approve. Turn it on from **Settings → Services**, which also
installs the himalaya mail program it uses. See [Email](./tools/email.md).

Any plugin that needs a program on your computer works the same way: its
card shows an **Install** button for that program, and nothing is
downloaded until you agree. The download is pinned to one version and
checked against a hash the plugin carries, and in mainland China it comes
from npmmirror first.

## Wake word

The Wake word plugin listens for a phrase such as "Hey Suzent" and starts
voice mode. Turning the wake word on under **Settings → Voice & audio**
installs it and downloads its model. Removing the plugin stops the listening
entirely, even if the setting is still on. See
[Start voice mode without clicking](../02-using/conversations.md#start-voice-mode-without-clicking).

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
