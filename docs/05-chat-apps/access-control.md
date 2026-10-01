---
sidebar_position: 6
title: Access control & pairing
description: Decide who can talk to your agent through a chat app, approve new people, and choose the model and tools chat apps use.
---

# Access control & pairing

**Sovereign authority.** A chat bot is a door into your agent, so Suzent keeps
it shut by default. Only the people you allow get through.

## Allowed users

Each chat app has its own list. In **Settings → Social Channels**, pick the app,
open the **Access control** tab, and enter the user IDs allowed to chat,
separated by commas. Each app's page explains how to find your ID.

Only user IDs count. Display names are ignored, because anyone can change
theirs. Messages from anyone else are refused.

## Letting new people ask for access

Turn on **Pairing & Access Control** if you want people who aren't on the list
to be able to ask:

1. A new person messages the bot. It greets them and asks them to introduce
   themselves.
2. When they reply, the bot gives them a short code and their request appears
   under **Pairing & Access Control**.
3. You click **Approve** or **Deny**. Once approved, they're added to that
   app's allowed users and can start chatting.

A code expires after 10 minutes. You can also handle requests from a terminal:

```bash
suzent pair list
suzent pair approve <code>
suzent pair deny <code>
```

With pairing turned off, only people already on an app's list can chat.

## Model and tools for chat apps

On the same settings page, **Social Model** picks the model chat-app
conversations use (or **Use Default System Model**), and **Agent Capabilities**
chooses which tools, memory tools, and MCP servers they may use. Keep these
tighter than your desktop chats if anyone other than you is on an allowed list.

Tool actions that need approval wait for `/approve` or `/deny` in the chat. See
[Commands in a chat app](./README.md#commands-in-a-chat-app).
