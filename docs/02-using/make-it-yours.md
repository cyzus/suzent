---
sidebar_position: 3
title: Making it yours
description: What to set up after your first chat, in the order most people need it, from cheaper models to backups.
---

# Making it yours

The [Quickstart](../01-getting-started/quickstart.md) gets you chatting with one
model. These are the next things worth setting up, roughly in the order most
people want them. Everything here is in **Settings**, at the bottom of the left
sidebar; [Settings pages](../07-reference/settings.md) lists them all.

## Spend less on routine work

Suzent runs small jobs in the background, such as titling chats and saving
memories. By default they use your main model. Set a cheaper, faster model as
the **Cheap** role in **Settings → Model Roles**, and those jobs use it
instead. See [Model roles](../04-models/model-roles.md).

To see what you're spending, open **Settings → Usage**, or type `/status` in a
chat.

## Keep your work safe

- **Choose a default permission mode.** The mode you pick on the new-chat
  screen, before sending anything, becomes the default for new chats. You can
  still change it in any chat. See [Permissions & approvals](../03-features/tools/human-in-the-loop.md).
- **Run code in a sandbox.** With Docker installed, turn the sandbox on in
  **Settings → Security** so commands run in an isolated container instead of
  on your computer. See [Using the sandbox](../03-features/filesystem.md#using-the-sandbox).

## Teach it about you

Tell the agent about yourself and your work in a chat; it remembers across
conversations. Check what it has kept in the **Memory** panel and correct
anything wrong. See [Memory](../03-features/memory/README.md).

For things you do often, add a [skill](../03-features/skills.md) so it follows
the same steps every time.

## Reach it from anywhere

- **From your phone or another computer:** see
  [Desktop, phone, and browser](../01-getting-started/platforms.md).
- **From a chat app** such as Telegram or Slack: see
  [Chat apps](../05-chat-apps/README.md).
- **Keep it running** after you close the window, so chat apps and scheduled
  tasks keep working: turn on **Settings → Background Service**. See
  [Automation](../03-features/automation.md#keep-suzent-running-in-the-background).

## Back it up

Turn on [GitHub Sync](../03-features/github-sync.md) in **Settings → Data & Sync**
to keep your settings, skills, and memory in a private repository you own. It
also moves them to a new computer. API keys are never synced.

## Look and language

**Settings → Appearance** switches between English and 简体中文, light or dark
theme, and the accent colors.
