---
sidebar_position: 12
title: Desktop apps
description: Let the agent read and operate native apps on your computer, using the accessibility tree. Off until you turn it on.
---

# Desktop apps

The agent can look at a native app the way a person would — buttons, menus,
text fields — and then click or type. It does this with
[agent-desktop](https://github.com/vercel-labs/agent-desktop) (Apache-2.0,
version 1.0.x), a separate program that reads the operating system's
accessibility tree. It is not the [browser](./browser.md) tool, and it does
not guess from screenshots.

This is off until you turn it on. Suzent never downloads or installs
agent-desktop for you.

## Turn it on

1. Install the agent-desktop 1.0.x command line yourself:

   ```bash
   npm install -g agent-desktop
   agent-desktop version
   ```

   Or download the release archive for your system from
   [GitHub Releases](https://github.com/vercel-labs/agent-desktop/releases)
   and put the program on your PATH. Keep the helper file that ships beside
   it. `agent-desktop version` should print JSON whose `data.version` starts
   with `1.0.`.

2. On a Mac, grant Accessibility permission. The guide opens System Settings
   on the right pane:

   ```bash
   agent-desktop permissions --guide
   ```

   Windows needs no extra grant for apps at the same privilege level as your
   terminal. Linux needs to be inside your graphical session, with the
   accessibility bus running (`at-spi2-core`).

3. In Suzent, open **Settings → Plugins** and install **Desktop**. From a
   terminal, `suzent plugin install desktop` does the same thing. Removing
   the plugin turns desktop control off.

The Desktop tool then shows up with your other tools. It is not in the set
that new chats enable on their own; tick it, or let the agent pick it up when
a task needs it. You can still deny it for one chat.

## What the agent can do

It snapshots an app, gets back a ref for each element it can use (they look
like `@s8f3k2p9:e8`), acts on that ref, and snapshots again to check. Reading
— a snapshot, a search, listing windows — runs on its own. Clicking, typing,
launching or closing an app, and anything else that changes the desktop asks
you first, using the same
[permission modes](./human-in-the-loop.md#permission-modes) as other actions:

| | **Ask** | **Smart** | **Full Access** |
|---|---|---|---|
| Read the screen, windows, or a field | Runs | Runs | Runs |
| Click, type, launch, close, or change a window | Asks | Reviewer | Runs |

In the background, where nobody can answer, a change the reviewer does not
clear is refused. Remembering "allow desktop click" remembers clicks, not
every desktop action.

By default the agent does not move your pointer or steal focus. Actions go
through the accessibility API. If a control can only be used with real
keyboard or pointer input, the agent can ask to run that step in headed mode,
which does move the pointer and can change which window is in front.

## Where it runs

Desktop actions always run on the computer where Suzent is running. They are
never sent into the [Docker sandbox](../filesystem.md#using-the-sandbox).
That container has no screen. Turning the sandbox on for shell commands does
not put a wall around the desktop: the agent is driving the apps you can see.

Snapshots, clipboard reads, and screenshots can contain whatever is on your
screen. Treat them as private.

## Limits to know about

- **Your real desktop.** There is no separate desktop session and no undo for
  a click. Close or save work you care about before you let the agent drive
  an app.
- **Linux Wayland.** The accessibility tree works. Pointer moves, drags, and
  most window moves or resizes do not: those need an X11 session. A Wayland
  clipboard needs `wl-clipboard`. Screenshots ask the portal the first time,
  and capturing one window is not supported there. Keyboard shortcuts work
  on GNOME Wayland.
- **Windows.** The release binary is unsigned. SmartScreen can warn when you
  download it, antivirus software can quarantine it, and Smart App Control on
  a clean Windows 11 install can block it. Check the file's checksum against
  the release if a scanner holds it, then choose **More info → Run anyway**,
  or restore it from quarantine.
- **Mac.** Accessibility must be granted, and a screenshot also needs Screen
  Recording permission. The temporary directory has to stay private to your
  user.
- **Refs go stale.** After the window changes, the agent has to take a new
  snapshot. A ref from an old snapshot is not reused.
- **Version.** Suzent talks to agent-desktop 1.0.x. A newer or older major
  version is refused until this integration is updated, so the agent is not
  guessing at a different command set.
- **Time limit.** One desktop command is stopped after three minutes, even if
  the CLI would have waited longer.

If the tool reports that agent-desktop is missing, install it yourself and
start the next message. Suzent will not run the installer in the background.
