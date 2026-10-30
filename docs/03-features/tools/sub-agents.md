---
sidebar_position: 7
title: Sub-agents
description: How the agent hands work to helper agents, what helpers can do, and how you watch, redirect, or stop them.
---

# Sub-agents

The agent can start a helper agent, a sub-agent, for a self-contained part of a
task: searching a codebase, researching a question, running the tests. Several
helpers can work at once, and their raw output stays out of your
conversation. Sub-agents are in the **Orchestration** group of the tool picker
and are on by default.

## Waiting or in the background

The agent chooses how each helper runs:

- **In the background** (the usual choice). The agent carries on, or finishes
  its turn, while the helper works. When the helper is done, the agent is woken
  up with the result and continues, even if you've moved on.
- **Waiting.** The agent pauses until the helper finishes, then uses its result
  straight away. Useful when the next step depends on it.

Either way, the result goes to the agent, not to you. The agent reads it and
tells you what matters.

If a helper's model goes quiet or drops the connection partway through, the
helper isn't stopped. It picks the task up again, up to three times. A helper
the agent was waiting on moves to the background at that point, so the agent
can carry on and is woken with the result when the helper finishes.

## Following up with a helper

A finished helper remembers what it read and did. When its work needs a fix,
a question answered, or a next step, the agent sends that helper a message
instead of starting a new one. The helper picks up where it left off, and its
reply comes back to the agent the same way its first result did: in the
background, or straight away if the agent chose to wait. The follow-up appears
in the helper's own chat.

## What a helper can and can't do

The agent gives each helper a written brief and a set of tools. It often picks
a ready-made profile, shown as a label on the helper in the chat:

| Profile | Tools |
|---|---|
| **EXPLORE** | Find, search, and read files |
| **PLAN** | Read files and research the web |
| **WRITE** | Read, create, and edit files |
| **VERIFY** | Run commands, such as tests or a build |
| **WEB** | Search the web and read pages |

A helper:

- starts with only its brief, unless the agent gives it a copy of the
  conversation so far (shown as **Context forked**);
- works in your chat's folder, or another folder the agent names (with the
  sandbox on, only one your chat can already reach). In a git project the
  agent can instead give the helper its own copy on a new branch; if the
  helper changes anything, that copy and branch are kept so you can review,
  merge, or delete them, and an untouched copy is cleaned up;
- doesn't start with your [memory](../memory/README.md) in its context, and
  can't start helpers of its own or manage other conversations;
- runs in **Smart** mode, since nobody is there to answer. It keeps the
  "for this session" and "always allow" answers you gave in your chat,
  and anything the reviewer can't clear is denied. See
  [When nobody is watching](./human-in-the-loop.md#when-nobody-is-watching).

A helper uses the same model as your chat, unless the agent picks another of
your enabled models for it. A helper can also be a
coding agent such as Claude Code or Codex, set up under **Settings → ACP
Agents** (see [Devices & other agents](../nodes.md#use-suzent-from-your-editor-acp)).

To use an external helper, install and sign in to it under **Settings → ACP
Agents**, then ask Suzent, for example: “Use Codex to investigate the failing
tests in this project.” Suzent can check which external agents are installed
before starting one. An installation check does not confirm that sign-in is
complete or that the agent can connect successfully.

For a follow-up, say “Ask the same helper to fix the failure.” Suzent sends the
instructions to the existing task. Background replies return to the parent
conversation automatically. External helpers use their own models and tools;
Suzent's native helper profiles do not control them. If this conversation
denies specific tools, external delegation is blocked because Suzent cannot
enforce that deny list inside the external agent.

## Watching, redirecting, and stopping helpers

Helpers appear as a block in the chat, with **View log** and **Stop**, and in
the **Background tasks** tab of the side panel, alongside background commands.
Each helper also has its own chat. In the chat list, a chat that started
helpers shows a button such as **2 subagents**; click it to show their chats.

Open a helper in **Background tasks** to see its task, tools, model, each tool
call as it happens, and its **Result**. While it runs you can:

- **Redirect it.** Type in **Redirect this sub-agent…** and click
  **Redirect**. The message is **Queued** and applies after its current step,
  then shows **Picked up**.
- **Stop it** with the **Stop** button.

## Other conversations and agents

The agent can also work with other agents, not just helpers it started:

- **Conversations in the same project.** It can list the ones that are running
  or recent, read their latest messages, send one a message (which wakes it up
  to reply), or stop one that's running. It can't reach chats in other
  projects.
- **Agents on other devices.** It can do the same with another Suzent you've
  allowed it to control, and hand work to A2A agents you've added. See
  [Devices & other agents](../nodes.md).
