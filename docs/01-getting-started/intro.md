---
sidebar_position: 1
title: What is Suzent?
---

# What is Suzent?

Suzent is a **sovereign AI agent** whose identity, memory, skills, workspace,
and runtime remain under your control. Models are replaceable, platforms are
temporary, and the continuity of your agent belongs to you.

## What is a sovereign AI agent?

A sovereign AI agent is an AI agent whose identity, memory, skills, workspace,
and runtime are owned and governed by its user rather than by a model provider
or platform. Its durable state lives in files you can read, edit, version, and
move; its actions run inside permission boundaries you define; and replacing the
underlying model does not reset the agent that knows your work.

The phrase "sovereign AI" is also used at the scale of nations, for
state-controlled models, data, and compute. A sovereign agent applies the same
idea at the scale of a person.

## Core ideas

**Sovereign** means more than running locally. Agent sovereignty has four
conditions — a sovereign mind, sovereign authority, a sovereign vessel, and
sovereign continuity. The full definition, and a five-question test for deciding
whether any agent meets it, is on
[what makes an agent sovereign](https://suzent.com/sovereign).

**Local agent** means it is built for more than one-off answers. It can keep long-term memory, schedule recurring work, and run the operations you explicitly allow.

## What makes it different

| Feature | Suzent |
|---|---|
| Model | Bring your own (GPT, Claude, Gemini, and more) |
| Memory | Persistent across sessions — markdown + semantic search |
| Automation | Built-in cron jobs and heartbeat monitoring |
| Storage | Local-first, sandboxed execution |
| Extensibility | Skills system for domain knowledge modules |
| Connectivity | Companion devices via Nodes (WebSocket) |

## How it fits together

```
You ──► Suzent Agent
             │
             ├── LLM of your choice (API key)
             ├── Memory (markdown + LanceDB)
             ├── Tools (file I/O, web, bash, social)
             ├── Skills (domain knowledge modules)
             ├── Automation (cron + heartbeat)
             └── Nodes (companion devices)
```

## Ready to try it?

Head to the [Quickstart](./quickstart) to be up and running in under 5 minutes.
