---
sidebar_position: 3
title: Desktop, phone, and browser
description: The ways to run and reach Suzent, from the desktop app to your phone, a browser, or a headless server.
---

# Desktop, phone, and browser

Suzent runs on one computer you own. That computer keeps the agent's memory,
files, and keys; every other way of reaching it is a window onto that same
agent.

| | What it is | Start here |
|---|---|---|
| **Desktop app** | The main app for Windows, macOS, and Linux. | [Quickstart](./quickstart.md) |
| **Phone** | The Suzent app for Android and iOS, paired with your computer. | [Mobile app](../03-features/mobile.md) |
| **Browser** | The same interface in a web browser, served by Suzent itself. | [Browser](#browser) |
| **Headless server** | Suzent running as a background service with no window. | [Headless server](#headless-server) |
| **Chat apps** | Telegram, Slack, Discord, Feishu, or WeChat. | [Chat apps](../05-chat-apps/README.md) |

## Phone

The Suzent app for Android and iOS (currently in preview) is a remote control
for the agent on your computer. Nothing runs on the phone itself, so your
memory and keys stay home. To get it and pair it, see
[Mobile app](../03-features/mobile.md).

## Browser

Run this on the computer where Suzent is installed:

```bash
suzent web
```

It opens Suzent in your browser. If the [background service](../03-features/automation.md#keep-suzent-running-in-the-background)
isn't installed yet, it offers to install it, so the page keeps working after
you close the terminal.

The browser version has the same chat and settings as the desktop app, laid out
as a console with a left-hand menu, plus an **Operations** page for checking
the service, reading its logs, and restarting it. A few things only the desktop
app can do, such as updating itself; in the browser, update Suzent by running
`suzent update` on that computer (see [Updating](./updating.md)).

### Opening it from another computer

Requests from the same computer are trusted. A browser on another machine has
to present a device token, just like any other device:

1. Make the computer reachable, as described in
   [Devices & other agents](../03-features/nodes.md#step-1-make-this-computer-reachable).
2. Create a host token in **Settings → Security**. It grants full access, so
   treat it like a password.
3. Open `http://<your-computer>:25314/?token=<token>` once. The browser keeps
   the token and removes it from the address bar.

Only do this on a network you trust, such as your home Wi-Fi or Tailscale.

## Headless server

To run Suzent on a machine you never sit in front of, install it as a
background service. It starts at sign-in and restarts itself if it crashes:

```bash
suzent service install
```

Then reach it from a browser as above, from your phone, or through a chat app.
`suzent service status` and `suzent logs` tell you how it's doing.
