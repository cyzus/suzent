---
sidebar_position: 3
title: Work on a folder safely
description: Point the agent at a folder on your computer, keep it on a short leash, and roll back anything you don't like with Git.
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

Review each request as it comes in. Choosing **This command · this chat** (or
**Allow all … for session**) from the arrow next to **Allow** saves you from
approving the same command again in this chat.

## 4. Take it back if you don't like it

Retry doesn't touch files, so keep the folder in Git. To undo the agent's
edits, run `git restore .` (or `git checkout -- .`) in the folder, or ask the
agent to revert them. The status bar at the bottom shows how many files have
changed in the folder's repository; click it to see which.

To have the agent try again, click the retry icon (↺) under its last reply.
Suzent rolls the conversation back to before that turn and runs your message
again. See
[Retrying the last turn](../03-features/filesystem.md#undoing-the-last-turn-retry).
