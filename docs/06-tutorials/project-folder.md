---
sidebar_position: 3
title: Work on a folder safely
description: Point the agent at a folder on your computer, keep it on a short leash, and undo anything you don't like.
---

# Work on a folder safely

**Sovereign vessel.** The agent can only touch what you hand it. This
walkthrough gives it one folder, makes it ask before every change, and shows
how to take a change back.

## 1. Give it the folder

In the chat box, click **Working Dir** and choose the folder, for example a
code project or a folder of documents. It's mounted for this conversation
only. See [Workspace & sandbox](../03-features/filesystem.md#giving-the-agent-access-to-your-folders).

## 2. Make it ask first

In the mode selector next to the message box, choose **Ask**. The agent can
read the folder freely, but every edit and every command waits for you. See
[Permission modes](../03-features/tools/human-in-the-loop.md#permission-modes).

Optional: to run its commands in an isolated container instead of directly on
your computer, turn on the sandbox for this chat (requires Docker). See
[Using the sandbox](../03-features/filesystem.md#using-the-sandbox).

## 3. Give it a job

> Read the README and the tests, then fix the failing test in `parser.py`.

Review each request as it comes in. **Allow for session** saves you from
approving the same command again in this chat.

## 4. Take it back if you don't like it

Click the retry icon (↺) under the agent's last reply. Suzent restores the
files the agent edited in that turn and runs your message again. See
[Undoing the last turn](../03-features/filesystem.md#undoing-the-last-turn-retry).

Retry only covers the last turn and only files the agent changed with its file
tools, so for real projects keep using Git as well.
