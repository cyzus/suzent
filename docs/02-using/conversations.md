---
sidebar_position: 1
title: Working with your agent
description: How to hand your agent a task, give it what it needs, steer it while it works, and recover when a turn goes wrong.
---

# Working with your agent

Suzent is an agent, not just a chatbot: it reads files, runs commands, searches
the web, and keeps going until the job is done. This page is about working with
it well.

## Hand it a task

Say what you want done and what "done" looks like. "Summarize these three
reports into a one-page brief in `brief.md`" gets better results than
"look at these reports".

- **One job per chat.** A chat keeps its whole history in view, so unrelated
  work in the same chat only adds noise. Start a new chat for a new job, and
  group related chats into a [project](./projects.md).
- **Tell it what you know.** Mention constraints, preferences, and where things
  are. What it learns about you is kept in [memory](../03-features/memory/README.md),
  so you don't have to repeat yourself next time.
- **Bigger jobs can run on their own.** For work that takes many steps, set a
  goal with `/goal` and the agent keeps working until it's met. For work that
  should repeat, schedule it. See [Automation](../03-features/automation.md).

## Give it the right material

The agent only sees what you give it.

| You want it to use | Do this |
|---|---|
| A document or image you have | Attach it, or paste the image into the message. It's kept in the project's folder. |
| A file it can already reach | Type `@` and part of the file name to point at it exactly. |
| A folder on your computer | Open it with **Working Dir** for this chat. |
| Something on the web | Just ask. It searches and reads pages on its own, and can use [a browser](../03-features/tools/browser.md). |

See [Workspace & sandbox](../03-features/filesystem.md) for what the agent can
reach and where its files go.

## Pick the model and effort for the job

Each chat has its own model, so you can use a strong model for hard work and a
fast, cheap one for quick questions. **Thinking** sets how long the model
reasons first: more effort is slower but more careful, and models that can't
reason ignore it.

Background work, such as titling chats and saving memories, uses the models you
set in [Model roles](../04-models/model-roles.md), not the chat's model.

## Decide how much it may do alone

Reading is always allowed. Before the agent changes anything, the chat's
permission mode decides whether it asks you:

- **Ask** when you want to see every change, for example in a folder you care
  about.
- **Smart** for everyday work: low-risk actions run, and a reviewer model checks
  the rest.
- **Full Access** only for work you'd be happy to let run unattended.

When it does ask, you can allow once, for the session, or always. See
[Permissions & approvals](../03-features/tools/human-in-the-loop.md).

## Steer while it works

You don't have to wait for a turn to finish. Type while the agent is working
and send it as a **Redirect**: the agent keeps what it has done so far and
continues with your correction. You can redirect or stop a single sub-agent the
same way, from its box in the chat.

## When a turn goes wrong

| What happened | What to do |
|---|---|
| The answer missed the point | Edit your last message and resend it, or **Retry**. The turn is rolled back, file edits included, and runs again. |
| The answer is fine but the file edits aren't | **Undo** on the "Edited files" card, or type `/undo`. Files go back; the conversation stays. |
| You want to try another direction and keep this one | **Branch from here** under any reply starts an independent copy from that point. |
| The chat has drifted too far | Start a new chat. Memory and the project folder carry over. |

Only the most recent turn can be retried or edited. Undo never overwrites a
file you've changed yourself since. See
[Undoing the last turn](../03-features/filesystem.md#undoing-the-last-turn-retry).

## Bring in another coding agent

A chat can be answered by Claude Code, Codex, or another installed coding agent
instead of one of your models: choose it under **ACP agents** in the model
picker of a new chat. That agent picks its own model and stays fixed for the
chat. See [Devices & other agents](../03-features/nodes.md#use-suzent-from-your-editor-acp).

All typed commands are listed in [Slash commands](../07-reference/slash-commands.md).
