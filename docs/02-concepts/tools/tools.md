---
sidebar_position: 1
title: Tools
description: What your agent can do (search, files, commands, browser, images, sub-agents) and how to turn each ability on or off.
---

# Tools

Tools are the actions your agent can take: searching the web, reading and
writing files, running commands, driving a browser, and more. You decide which
ones each conversation can use, and anything that changes your files or the
outside world asks first (see [Permissions & approvals](./human-in-the-loop.md)).

## Turning tools on and off

Open the tool picker in a chat's settings. Tools are grouped by capability:
click a group's header to toggle the whole group, or tick tools one by one.

A sensible set is on by default: web search, files, commands, tasks and goals,
images, sub-agents, and memory search. You don't have to enable everything up
front. When a task needs a tool that is switched off, the agent can turn it on
for the rest of that conversation by itself.

## What's available

| Capability | What the agent can do |
|---|---|
| **Filesystem** | Read files (including PDF, Word, Excel, PowerPoint, and text in images), create and edit files, and search by name or content. See [Workspace & sandbox](../filesystem.md) for which folders it can reach. |
| **Shell** | Run commands, or start long-running ones in the background and check on them later. |
| **Web** | Search the web, read pages, and drive a browser, either its own or yours. See [Browser](./browser.md). |
| **Tasks & goals** | Break work into tracked tasks, pursue a [goal](../automation.md#goal-mode) across many turns, and schedule its own follow-ups. |
| **Orchestration** | Load [skills](../skills.md) and hand work to [sub-agents](#sub-agents). |
| **Interaction** | Ask you a focused question, or show tables, forms, cards, and buttons in the sidebar or chat. Your clicks and form answers go straight back to the agent. |
| **Creative** | Generate and edit images, create videos, read text aloud, and send messages through your [chat apps](../social-messaging/README.md). See [below](#images-video-and-speech). |
| **Memory & recall** | Search what it remembers and find relevant past conversations. See [Memory](../memory/README.md). |

## Web search

Web search works out of the box using DuckDuckGo. For more private or more
reliable results, run your own [SearXNG](https://docs.searxng.org/) instance and
set `SEARXNG_BASE_URL` in your `.env` file; Suzent uses it automatically.

## Background commands

Long-running commands, such as a build or a dev server, can run in the
background while you keep chatting. The **Background tasks** sidebar shows
each command's live output, exit code, and a Stop button, alongside any
sub-agents. When a background command finishes, the agent is told and picks up
where it left off, even if you have moved on.

## Sub-agents

The agent can start a helper agent for a self-contained part of a task, either
waiting for it or letting it run in the background. Helpers appear in the
**Background tasks** sidebar. The agent can also check on, message, or stop
other conversations in the same project, and agents on
[paired devices](../nodes.md).

## Images, video and speech

These tools need their own models. Assign them in
**Settings → Model Roles** (see [Model roles](../providers/model-roles.md)),
then enable the tools in the tool picker.

**Images.** Ask for an image and the agent generates it with your
**Image Generation** model. To change an existing picture, attach it and
describe the edit; this uses the **Image Editing** model. Results are saved in
the workspace's `images` folder.

**Video.** Assign a **Video generation** model, then ask, for example, "Generate
an 8-second landscape video of mist moving through a forest." Video is a paid,
slow job: the agent submits it, checks back, and shows the finished video in
the chat. To animate a picture, attach it and ask to use it as the reference.

**Speech.** The agent can read text aloud in two ways, configured in
**Settings → Voice & audio**:

- **System** uses voices already installed on your device. No model or API key
  is needed.
- **API** uses your **TTS** model for higher-quality voices and saves the audio
  so you can replay it.

New speech plays automatically. Turn off **Automatically play new tool speech**
in the same settings if you prefer to press Play yourself.

## MCP servers

Suzent can use tools from any [MCP](https://modelcontextprotocol.io/) server.
Open **Settings → MCP Servers**, add the server's command (or URL), click
**Test**, and enable it for the conversations that need it.
