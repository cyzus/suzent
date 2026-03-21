---
sidebar_position: 1
title: What is Suzent?
---

# What is Suzent?

Suzent is a **sovereign digital coworker** — a local-first AI agent you own and control entirely. No cloud lock-in, no data leaving your machine unless you choose.

## Core ideas

**Sovereign** means you run it. Your model keys, your data, your infrastructure. Suzent doesn't phone home.

**Digital coworker** means it's built to work *with* you over time — not just answer one-off questions. It remembers past sessions, schedules recurring tasks, and can monitor things while you sleep.

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
