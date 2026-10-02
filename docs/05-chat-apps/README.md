---
sidebar_position: 7
title: Chat apps
description: Talk to your agent from Telegram, Slack, Discord, Feishu (Lark), or WeChat.
---

# Chat apps

Talk to your agent from the chat apps you already use. It's the same agent,
with the same memory and files, whether you're at your desk or on your phone.

| App | Supports |
|---|---|
| [Telegram](./telegram.md) | Text, photos, files |
| [Slack](./slack.md) | Text, files, threads |
| [Discord](./discord.md) | Text, files, DMs and channels |
| [Feishu (Lark)](./feishu.md) | Text, files |
| [WeChat](./wechat.md) | Text, images |

## How it works

1. Create a bot in the app. Each app's page has the steps.
2. In Suzent, open **Settings → Social Channels**, pick the app, paste the
   bot's credentials on the **Connection** tab, and enable it.
3. On the **Access control** tab, add your own user ID to **Allowed users**.

Suzent keeps these settings in `config/social.json`, which you can also edit by
hand. `config/social.example.json` shows every option.

**Only people you allow can talk to your agent.** Messages from anyone not on
the app's allowed list are refused. See [Access control & pairing](./access-control.md)
for letting others in, and for choosing which model and tools chat apps use.

**Conversations persist.** Each chat becomes a regular Suzent conversation that
remembers its history, even after a restart. Photos are read by the model if it
supports images. Files you send are saved to the project library's
`uploads` folder, where the agent can open them.

## Commands in a chat app

Send these as messages to the bot:

| Command | What it does |
|---|---|
| `/approve` (or `/y`) | Approve the action the agent is waiting on. `/ya` also allows it for the rest of the conversation. |
| `/deny` (or `/n`) | Refuse it. |
| `/new [title]` | Start a fresh conversation. |
| `/sess ls`, `/sess switch <id>`, `/sess info` | List your conversations, switch to another, or show the current one. |
| `/retry` | Redo the agent's last answer. |
| `/model [id]` | Show or change the model for this conversation. |
| `/goal <goal>` | Give the agent a [goal](../03-features/automation.md#goal-mode) to keep working on. |
| `/status` | Check that Suzent is healthy. |
| `/help` | List every command. |

## Keep it online

Chat apps only work while Suzent is running. To keep them available after you
close the window, turn on the [background service](../03-features/automation.md#keep-suzent-running-in-the-background).
