---
sidebar_position: 2
title: Organizing work into projects
description: Use projects to give related chats a shared folder, standing context, and one board of goals and tasks.
---

# Organizing work into projects

A project is how you keep one piece of ongoing work together, such as a
report, a codebase, or a trip you're planning. Every chat in a project shares
three things:

- **A library folder.** Notes and deliverables saved in one chat are there in
  the next, and other projects can't see them. See
  [What goes in the project library](../03-features/filesystem.md#what-goes-in-the-project-library).
- **Project context.** A short note, `context.md` in the project folder, that
  every chat in the project reads first. The agent keeps it up to date with the
  project's goal, current state, decisions, and a list of the files in the
  library.
- **A board** of the project's goals and tasks, from every chat.

## When to start a project

Start one when work will span more than one chat, or when it has files you
want kept apart from everything else. Quick, one-off questions are fine in
**Home**, the project new chats go to by default. Chats that arrive from
[chat apps](../05-chat-apps/README.md) go to **Social**.

Create a project from the **Projects** list in the sidebar, or pick one on the
new-chat screen. A chat can be moved to another project later; deleting a
project moves its chats to **Home**.

To move or delete several chats at once, select them the way you would select
files on your computer:

- **macOS:** ⌘-click adds a chat, ⇧-click selects a range, ⌘A selects every
  chat in view, and ⌘⌫ deletes the selection.
- **Windows and Linux:** Ctrl-click adds a chat, Shift-click selects a range,
  Ctrl+A selects every chat in view, and Delete deletes the selection.
- **Touch screens:** press and hold a chat, then tap others to add them.

You can also choose **Select chats** from the **⋯** menu next to the list, or
**Select** from a chat's right-click menu. While chats are selected, a bar at
the bottom of the sidebar offers **Move** and **Delete**, and right-clicking any
selected chat acts on all of them. Press Esc or **Done** to stop selecting.

## Give it standing instructions

Project context is the place for anything every chat should know: the goal,
the audience, decisions already made, conventions to follow. Open the
**Context** tab in the chat's side panel and click **Edit** to write it
yourself, or ask the agent to note something there.

When the agent works in a folder that has an `AGENTS.md` or `CLAUDE.md` file, it
follows those instructions too. If there are several, the one closest to the
working folder wins.

Project context is about this project. What the agent learns about *you* is
kept in [memory](../03-features/memory/README.md) and applies everywhere.

## Track the work on the board

Set a goal with `/goal` and the agent keeps working until it's met. The
**Goal** tab shows this chat's goal and the tasks assigned to it, with
**Pause**, **Resume**, and **Clear**. **Open Board** shows every task in the
project, from every chat, so you can see where the whole project stands and add
or move tasks yourself. See [Goal mode](../03-features/automation.md#goal-mode).

## Keep an eye on what it's doing

The chat's side panel shows what the agent is working with: its files, the
pages it read, interactive panels it shows you on the **Canvas**, and commands
or sub-agents running in the background. Open a background task to follow it,
stop it, or redirect a sub-agent.
