---
sidebar_position: 12
title: Desktop apps
description: Let the agent read and operate native apps on your computer, using the accessibility tree. Off until you turn it on.
---

# Desktop apps

The agent can look at a native app the way a person would — buttons, menus,
text fields — and then click or type. It does this with
[agent-desktop](https://github.com/vercel-labs/agent-desktop) (Apache-2.0,
version 1.x), a separate program that reads the operating system's
accessibility tree. It is not the [browser](./browser.md) tool, and it does
not guess from screenshots.

This is off until you turn the Desktop plugin on. Suzent can download
agent-desktop for you, but only after you agree. It never downloads it in
the background when the agent tries to use the tool.

## Turn it on

1. In Suzent, open **Settings → Plugins** and install **Desktop**. From a
   terminal, `suzent plugin install desktop` does the same thing. Removing
   the plugin turns desktop control off.

2. The plugin card then shows **Install agent-desktop**. Suzent asks before
   it downloads the **agent-desktop** release pinned in the plugin, the same package npm publishes,
   into its own folder. It checks the download against a SHA-256 written
   into the plugin, so a copy from any source has to be byte-for-byte that
   release. Only the program for this computer and the helper file that has
   to sit beside it are kept. On a Mac, the Accessibility guide opens after
   a successful install.

   When Suzent detects it is in mainland China (the same check setup uses,
   see [Quickstart](../../01-getting-started/quickstart.md)), the download
   comes from npmmirror first and falls back to npm; otherwise the other way
   round.
   No GitHub access is needed either way.

   From a terminal, `suzent plugin install desktop` asks the same question
   after it turns the plugin on. Add `--yes` only when you have already
   agreed.

   On Windows that file is unsigned. SmartScreen, antivirus software, or
   Smart App Control may block it. The confirmation says so before anything
   is downloaded.

3. You can still install it yourself and leave Suzent out of it:

   ```bash
   npm install -g agent-desktop
   ```

   Or point Suzent at a copy you already trust:

   ```bash
   export SUZENT_AGENT_DESKTOP_BIN=/path/to/agent-desktop
   ```

   That path is used as-is. A program already on your PATH is used when
   Suzent has not installed its own copy and the variable is unset.

4. On a Mac, if the guide did not open, grant Accessibility yourself:

   ```bash
   agent-desktop permissions --guide
   ```

   Windows needs no extra grant for apps at the same privilege level as your
   terminal. Linux needs to be inside your graphical session, with the
   accessibility bus running (`at-spi2-core`).

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
  a clean Windows 11 install can block it. If a scanner holds it, then choose **More info → Run anyway**,
  or restore it from quarantine.
- **Mac.** Accessibility must be granted, and a screenshot also needs Screen
  Recording permission. The temporary directory has to stay private to your
  user.
- **Refs go stale.** After the window changes, the agent has to take a new
  snapshot. A ref from an old snapshot is not reused.
- **Version.** Suzent talks to agent-desktop 1.x. A newer or older major
  version is refused until this integration is updated, so the agent is not
  guessing at a different command set.
- **Time limit.** One desktop command is stopped after three minutes, even if
  the CLI would have waited longer.

If the tool reports that agent-desktop is missing, install it yourself and
start the next message. Suzent will not run the installer in the background.
