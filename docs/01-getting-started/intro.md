---
sidebar_position: 1
title: What is Suzent?
---

# What is Suzent?

Suzent is a **sovereign local agent** — a local-first AI system you own and control entirely. No cloud lock-in, no data leaving your machine unless you choose.

## Core ideas

**Sovereign** means the important controls stay with you: model keys, data, memory, and runtime.

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
