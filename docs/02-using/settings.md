---
sidebar_position: 3
title: Settings at a glance
description: Every page in Suzent's settings, what it's for, and where to read more.
---

# Settings at a glance

Open **Settings** from the bottom of the left sidebar. Pages are grouped into
**Agent**, **Connections**, and **Application**.

## All settings pages

| Page | What it's for | More |
|---|---|---|
| **Providers** | Add API keys, sign in to providers, and choose which models are available. | [Models & Providers](../04-models/README.md) |
| **Model Roles** | Pick which model handles each kind of work, with backups. | [Model roles](../04-models/model-roles.md) |
| **Voice & audio** | Choose how the agent's speech sounds and plays. | [Images, video and speech](../03-features/tools/tools.md#images-video-and-speech) |
| **Memory System** | Turn memory tools on or off, see which models memory uses, and choose the notebook folder. | [Memory](../03-features/memory/README.md) |
| **Automation** | Create and manage scheduled tasks, and choose which tools heartbeats may run without review. | [Automation](../03-features/automation.md) |
| **Social Channels** | Connect Telegram, Slack, Discord, Feishu, or WeChat, and control who may chat. | [Chat apps](../05-chat-apps/README.md) |
| **MCP Servers** | Add and test servers that give the agent extra tools. | [MCP servers](../03-features/tools/tools.md#mcp-servers) |
| **Browser** | Choose how the agent connects to a browser. | [Browser](../03-features/tools/browser.md) |
| **ACP Agents** | Set up coding agents such as Claude Code or Codex to use in chats. | [The chat window](./chat.md#chatting-with-claude-code-codex-and-other-agents) |
| **Devices** | Pair your phone and connect other devices. | [Devices & other agents](../03-features/nodes.md) |
| **Mesh** | Make this computer reachable on your network, and work with other agents. | [Devices & other agents](../03-features/nodes.md) |
| **Appearance** | Theme, color scheme, and language. | [Below](#appearance) |
| **Background Service** | Keep Suzent running after you close the window. | [Automation](../03-features/automation.md#keep-suzent-running-in-the-background) |
| **Security** | Turn the sandbox on for every chat, and create host tokens for remote administration. | [Workspace & sandbox](../03-features/filesystem.md), [Permissions & approvals](../03-features/tools/human-in-the-loop.md) |
| **Data & Sync** | Sync your settings, skills, and memory through GitHub. | [GitHub Sync](../03-features/github-sync.md) |
| **Usage** | See what you've spent and how many tokens you've used. | [Below](#usage) |
| **About** | Version information and updates. | [Below](#about) |

Permission modes and approval rules aren't on a settings page. You set the mode
per chat, under the message box, and save rules as you answer requests (see
[Permissions & approvals](../03-features/tools/human-in-the-loop.md)).

### In the web console

When you use Suzent in a web browser instead of the desktop app, settings
pages are listed in the console's own sidebar. Two pages work differently
there:

- **Browser** isn't shown.
- **Background Service** is replaced by **Operations**, which shows the
  background service's status, lets you restart it, and shows its log.

## Usage

**Usage** shows what your model calls cost and how many tokens they used.
Choose a period at the top: 1, 7, or 30 days, or all time.

- **Total Spend**, **Avg. Daily**, **API Calls**, and **Tokens** sum up the
  period.
- **Daily Spend** charts your spending day by day.
- **Token Breakdown** splits tokens into **Input Tokens** and **Output Tokens**.
  A per-model list shows how much each model used.
- **Token Activity** is a heatmap of when you used Suzent, in UTC.

If the page says **No usage data yet**, start chatting and come back.

## Appearance

| Setting | Options |
|---|---|
| **Language** | English or 简体中文 (Simplified Chinese). |
| **Theme** | **Light**, **Dark**, or **System** to follow your computer. |
| **Color Scheme** | The accent colors: **Warm**, **Cold**, or **Green**. |

## About

**About** shows the version of the **Desktop frontend** and the **Python
backend**. If the two ever don't match, Suzent tells you when it starts and
asks you to run `suzent update`.

Under **Software updates**, **Check for updates** looks for a newer release.
If there is one, click **Update**: Suzent closes, updates, and restarts on its
own. In the web console there's nothing to install from here; update the
computer that runs Suzent instead (see [Updating](../01-getting-started/updating.md)).
