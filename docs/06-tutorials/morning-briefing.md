---
sidebar_position: 2
title: Get a morning briefing on Telegram
description: Schedule a task that prepares a short briefing every weekday and sends it to you on Telegram.
---

# Get a morning briefing on Telegram

This walkthrough combines a [chat app](../05-chat-apps/README.md) with a
[scheduled task](../03-features/automation.md#scheduled-tasks), so a short
briefing arrives on your phone every weekday morning.

## 1. Connect Telegram

Follow the [Telegram](../05-chat-apps/telegram.md) steps to create a bot and
add your user ID to **Allowed users**. Then send your bot a message, such as
"hi". The agent can only message people who have talked to it.

## 2. Let the agent send you messages

Sending a message is an action, so it needs your approval. In a desktop chat,
ask:

> Send me a test message on Telegram.

When the approval request appears, choose **Always allow**. Scheduled tasks run
with nobody watching, and this saved rule lets them send without waiting for
review (see [Permissions & approvals](../03-features/tools/human-in-the-loop.md#answering-a-request)).

## 3. Schedule the briefing

Ask the agent in plain words:

> Every weekday at 8:00, check the weather for Berlin and the top tech news,
> then send me a five-line briefing on Telegram.

Or create it yourself in **Settings → Automation**: set a **daily** or cron
schedule (`0 8 * * 1-5` is weekdays at 8:00), set your time zone, and write a
prompt that stands on its own, since the task runs in its own chat.

## 4. Keep Suzent running

The task only runs while Suzent is running. If you close the app at night,
turn on the [background service](../03-features/automation.md#keep-suzent-running-in-the-background).

## If nothing arrives

- Check the task in **Settings → Automation**. A failed run shows its error
  there.
- Make sure you have messaged the bot at least once.
- Make sure your Telegram user ID is in **Allowed users**.
