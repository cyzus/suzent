---
sidebar_position: 1
title: Model roles
description: Choose which model handles each kind of work, from your main conversations to memory, images, and speech.
---

# Model roles

Not every job needs your biggest model. **Settings → Model Roles** lets you
assign a model to each kind of work, so routine background jobs can run on a
small, cheap model while your conversations use the best one you have.

| Role | Used for | If left empty |
|---|---|---|
| **Primary** | Your conversations. Needs tool use and a large context window. | Required |
| **Cheap** | The default for lightweight background jobs. A small, fast model is ideal. | Primary |
| **Title** | Naming your conversations. | Cheap |
| **Input Suggestion** | Guessing your next message, shown in grey in the chat box. Open the row to turn the suggestions off. | Cheap |
| **Memory Extraction** | Picking out facts worth remembering after each turn. | Cheap |
| **Decision** | Quick yes-or-no calls: whether a [goal](../03-features/automation.md#goal-mode) is done, whether a tool call is safe to [approve automatically](../03-features/tools/human-in-the-loop.md), and, after each reply in a project conversation, whether it is waiting on you. | Cheap |
| **Goal Judge**, **Permission Review** | Override Decision for just one of those calls. Found under **Advanced decision roles**. | Decision |
| **Memory organizer** | Overnight [memory consolidation](../03-features/memory/README.md#how-memory-is-tidied). | Primary |
| **Vision** | Reading images. | Primary, if it can see images |
| **Embedding** | Memory search. | Nothing; assign one to use memory search |
| **Image Generation**, **Image Editing**, **Video generation**, **TTS** | The [creative tools](../03-features/tools/media.md). | Nothing; assign one to use the tool |
| **Decision model** | Optional. A [decision model](#decision-models) that routes new kinds of [Mailbox](../03-features/mailbox.md) events. | Decision does it |

## Decision models

A decision model doesn't write text: it picks from fixed choices and says how
sure it is, in a few hundred milliseconds and for a fraction of a chat model's
cost. Suzent supports two:

- **OpenAI**: `openai/gpt-6-luna`, through OpenAI's Decisions API.
- **Gemini**: `gemini/gemini-decision-1`, through the Gemini Decisions API.

Both use the API key you added for that provider in **Settings → Providers**.
Pick one under **Decision model** in **Settings → Model Roles**. Today it routes
the first event of each new kind in the Mailbox. When it isn't sure of its
choice, the event goes to Regent and no rule is saved, so the next event of that
kind is decided again. If it fails or isn't set, the **Decision** role does the
job instead.

A decision model can't chat, so it is never offered for the other roles.

## Backups

Each role can also hold backup models. If the first one fails, Suzent tries the
next in order.
