---
sidebar_position: 1
title: Tools
description: What your agent can do, how to choose which tools a chat may use, and where to read about each one.
---

# Tools

Tools are the actions your agent can take: reading and writing files, running
commands, searching the web, driving a browser, and more. You choose which
ones each chat may use, and anything that changes your files or the outside
world asks first (see [Permissions & approvals](./human-in-the-loop.md)).

## What's available

| Group | What the agent can do | Read more |
|---|---|---|
| **Filesystem** | Read files, including PDFs and Office documents, write and edit them, and find files by name or content. | [Files](./files.md) |
| **Shell** | Run commands, or start long ones in the background and check on them later. | [Commands](./shell.md) |
| **Web** | Search the web, read pages, and drive a browser. | [Web search & pages](./web.md), [Browser](./browser.md) |
| **Orchestration** | Hand work to helper agents and load [skills](../skills.md). | [Sub-agents](./sub-agents.md) |
| **Tasks & goals** | Track tasks, pursue a goal across many turns, and schedule its own follow-ups. | [Tasks & planning](./tasks.md) |
| **Interaction** | Ask you a focused question, or show tables, forms, and buttons you can answer. | [Questions, canvas & messages](./interaction.md) |
| **Creative** | Generate and edit images, make videos, speak, and send messages through your chat apps. | [Images, video & speech](./media.md) |
| **Memory & recall** | Search what it remembers and find past conversations. | [Memory](../memory/README.md) |

Tools from [MCP servers](./mcp.md) you add appear alongside these.

## Choosing tools for a chat

Open the right sidebar with **Open Sidebar** and go to the **Tools** tab. Tick a
group to switch all its tools on or off, or tick tools one by one.

A sensible set is on by default: web search, files, commands, tasks and goals,
image generation and editing, sub-agents, and memory search. **Skill** and
**Ask Question** are always on.

You don't have to switch everything on up front. When a task needs a tool
that's off, the agent can find it and turn it on for that chat by itself. Those
tools show an **AI** mark, with a **Deactivate** button if you'd rather it
didn't. A tool the agent turns on still asks for approval as usual.

Commands and **Social Message** are the exception: when you switch them off,
they show **Off** and the agent can't turn them back on.
