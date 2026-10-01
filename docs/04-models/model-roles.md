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
| **Memory Extraction** | Picking out facts worth remembering after each turn. | Cheap |
| **Decision** | Quick yes-or-no calls: whether a [goal](../03-features/automation.md#goal-mode) is done, and whether a tool call is safe to [approve automatically](../03-features/tools/human-in-the-loop.md). | Cheap |
| **Goal Judge**, **Permission Review** | Override Decision for just one of those calls. Found under **Advanced decision roles**. | Decision |
| **Dream** | Overnight [memory consolidation](../03-features/memory/README.md#how-memory-is-tidied). | Primary |
| **Vision** | Reading images. | Primary, if it can see images |
| **Embedding** | Memory search. | Nothing; assign one to use memory search |
| **Image Generation**, **Image Editing**, **Video generation**, **TTS** | The [creative tools](../03-features/tools/media.md). | Nothing; assign one to use the tool |

## Backups

Each role can also hold backup models. If the first one fails, Suzent tries the
next in order.
