---
sidebar_position: 9
title: Questions, canvas & messages
description: How the agent asks you a focused question, shows tables, forms, and buttons you can click, and sends messages through your chat apps.
---

# Questions, canvas & messages

Besides writing replies, the agent can ask you a question with clickable
answers, show you an interactive panel, and send a message through one of
your chat apps.

## Questions

When the agent needs a decision from you, it can ask instead of guessing. The
question appears in the chat, and the agent pauses for your answer.

- **One question with choices** shows one button per choice. Click one.
- **Several questions** show as a short form, one question per page, with
  **Next →**, **← Back**, and **Submit**.
- A question can allow more than one choice (tick boxes), or offer
  **Type something else…** so you can write your own answer.

Your answer goes straight back to the agent, and it waits as long as you need.
Where nobody can click an answer (sub-agents, scheduled tasks, goals, and
chats in a chat app), the agent asks in its reply instead, or carries on with
an assumption it states. Asking a question needs no
approval, and it is always on: the tool picker shows it ticked under
**Interaction**, and it can't be switched off.

## The canvas: tables, forms, cards, and buttons

The agent can build a small interface for you: a table of results, a form to
fill in, cards, lists, progress bars, and buttons. For anything richer, such as
a chart or a custom dashboard, it can build a self-contained web page that runs
in a sealed-off frame.

These normally appear right in the chat. Each one has two buttons in its
header: **Open in side panel** moves a copy to the **Canvas** tab of the side
panel, so it stays in view while you keep chatting, and **Fullscreen** gives it
the whole window. When the agent shows a newer version of the same panel
later on, the older one folds down to a single line you can expand again.

For something you'll want to watch as work progresses, such as a live progress
board, the agent can put the panel straight into the Canvas tab and leave a
small card in the chat to reopen it from. When there are several on the
Canvas, a tab strip at the top switches between them.

Clicking a button or submitting a form sends your action and any form values
to the agent as a new message, and it responds. This tool is **Render UI** in
the **Interaction** group of the tool picker. It's off by default, but the
agent can switch it on when it needs it.

## Sending a message through a chat app

The agent can send a message through a [chat app](../../05-chat-apps/README.md)
you've connected, such as Telegram, Slack, Discord, Feishu, or WeChat. For
example: "Message me on Telegram when the backup finishes."

- **It asks first.** Sending a message counts as changing the outside world,
  so in **Ask** mode you approve each one, and in **Smart** mode the reviewer
  checks it (see [Permissions & approvals](./human-in-the-loop.md)).
- **Who it can reach.** The agent can see which apps are connected and the
  people from your recent chat-app conversations, and send to one of them.
- **In a chat-app conversation**, the agent's final reply is sent back to that
  conversation automatically. It uses this tool only for progress updates while
  it works, and it's switched on there for you.
- **Long messages are cut** to fit the app: 2,000 characters on Discord, 4,096
  on Telegram, 30,000 on Feishu and WeChat, and 40,000 on Slack. Sources the
  agent cites are written out as plain text.

Elsewhere, enable **Social Message** in the **Creative** group of the tool
picker.
