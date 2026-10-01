---
sidebar_position: 2
title: Slash commands
description: Every command you can type into a chat, what it does, and whether it works in the desktop app, chat apps, or the terminal.
---

# Slash commands

Type a slash command as a message, starting with `/`. Suzent handles it
directly instead of sending it to the model. In the desktop app, typing `/`
in the message box shows the commands available there, and `/help` lists them
anywhere.

The **Works in** column uses these names:

- **Desktop**: the chat in the desktop app or web browser.
- **Chat apps**: Telegram, Slack, Discord, Feishu, and WeChat. See
  [Chat apps](../05-chat-apps/README.md).
- **Terminal**: `suzent agent chat`. See [Command line](./cli.md#chatting-from-the-terminal).

A command typed where it doesn't work is sent to the agent as an ordinary
message.

## Conversation

| Command | What it does | Works in |
|---|---|---|
| `/help` (also `/h`, `/?`) | List the commands available here. | Everywhere |
| `/status` (also `/stat`) | Show Suzent's health, plus this conversation's model, context use, tokens, and cost. | Everywhere |
| `/model` | Show the model this conversation uses. | Everywhere |
| `/model ls` | List your enabled models. | Everywhere |
| `/model <model-id>` | Switch this conversation to another model. Part of a name is enough if it matches only one model. | Everywhere |
| `/compact [focus]` | Summarize the conversation so far to free up context. Add text to say what the summary should focus on. | Everywhere |
| `/clear` (also `/reset`) | Clear this conversation's history so new messages start fresh. | Desktop, Terminal |
| `/fork` | Make an independent copy of this conversation. In a chat app, you are switched to the copy. | Everywhere |

## Undo and retry

| Command | What it does | Works in |
|---|---|---|
| `/retry` | Roll back the last turn, including files the agent changed, and run your message again. The retry button under the agent's reply does the same. | Everywhere |
| `/retry-edit <text>` | Like `/retry`, but runs `<text>` instead of your original message. Editing your last message in the desktop app does this. | Everywhere |
| `/undo` | Undo the file changes from the agent's last turn, without rerunning it. It stops if a file was changed again since then. | Everywhere |

Only the last turn can be undone. Changes made by shell commands aren't rolled
back. See [Undoing the last turn](../03-features/filesystem.md#undoing-the-last-turn-retry).

## Goals

Goal mode keeps the agent working across turns until an objective is met. See
[Goal mode](../03-features/automation.md#goal-mode).

| Command | What it does | Works in |
|---|---|---|
| `/goal <objective>` | Set a goal. The agent starts working on it right away. | Everywhere |
| `/goal` or `/goal status` | Show the current goal and its progress. | Everywhere |
| `/goal pause` | Pause the goal. | Everywhere |
| `/goal resume` | Resume it with a fresh turn budget. | Everywhere |
| `/goal clear` | Remove the goal. | Everywhere |
| `/subgoal <text>` | Add a condition that must also be met. | Everywhere |
| `/subgoal` | List the extra conditions. | Everywhere |
| `/subgoal remove <N>` | Remove condition number N. | Everywhere |
| `/subgoal clear` | Remove all extra conditions. | Everywhere |

## Chat apps only

These commands exist because a chat app has no buttons for switching
conversations or answering a permission request.

| Command | What it does | Works in |
|---|---|---|
| `/approve [id]` (also `/y`, `/yes`, `/allow`) | Approve the action the agent is waiting on. | Chat apps |
| `/ya` | Approve it and remember the answer for the rest of the conversation. | Chat apps |
| `/deny [id]` (also `/n`, `/no`, `/reject`) | Refuse the action. | Chat apps |
| `/new [title]` | Start a new conversation and switch to it. | Chat apps |
| `/sess ls` | List your conversations. | Chat apps |
| `/sess switch <id>` | Switch to another conversation. | Chat apps |
| `/sess new [title]` | Same as `/new`. | Chat apps |
| `/sess info` or `/sess` | Show the current conversation. | Chat apps |

In the desktop app and the terminal, you answer permission requests when they
appear instead. See [Permissions & approvals](../03-features/tools/human-in-the-loop.md).

## Devices

| Command | What it does | Works in |
|---|---|---|
| `/node list` | List connected devices. | Desktop, Terminal |
| `/node status` | Show device connectivity. | Desktop, Terminal |
| `/node describe <device>` | Show what a device can do. | Desktop, Terminal |
| `/node invoke <device> <command>` | Run one of a device's commands. | Desktop, Terminal |

See [Devices & other agents](../03-features/nodes.md).
