---
sidebar_position: 13
title: Code mode
description: Let the agent batch many look-ups in one short Python snippet instead of calling tools one at a time.
---

# Code mode

When a task needs many look-ups, such as reading a dozen files or searching
the web for each item in a list, the agent normally calls one tool, waits for
the answer, and calls the next. With code mode on, it can instead write one
short Python snippet that makes all those calls, loops over the results, and
hands back only what matters. That usually means fewer round trips to the
model, so the work is faster and uses fewer tokens.

Code mode is off by default.

## Turning it on

Open **Settings**, go to **Model Roles**, and switch on **Code mode (experimental)** under
**Agent behavior**. It applies to new messages in every chat.

## What a snippet can do

A snippet runs in a sandbox with no access to your files, network or
commands of its own. It can only call these tools, all of which just read:

- reading files and finding them by name or content
- web search and reading web pages
- searching memory and past conversations
- listing tasks and checking on helper agents
- watching videos you've shared
- searching and reading your email

Anything that changes your files or the outside world, such as writing files,
running commands or sending messages, stays an ordinary tool call, and still
asks for your approval as usual. So turning on code mode never lets the agent
skip an approval.

## What you see

A snippet shows in the chat as a **Run code** step with the Python it ran.
Each tool the snippet calls appears right under it, indented, as it starts
and finishes, just like a tool the agent calls directly. They are still
there when you reopen the chat.

## Good to know

- The agent decides when a snippet helps. For one or two look-ups it still
  calls tools directly.
- The list of tools a snippet can call is sent to the model with every
  message, which adds a few thousand tokens to each request.
- A snippet's own code stops after 30 seconds. Time spent waiting on the
  tools it calls doesn't count toward that.
