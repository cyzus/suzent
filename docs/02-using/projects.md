---
sidebar_position: 2
title: Projects & the sidebar
description: Group chats into projects, keep the chat list tidy, and use the right-hand sidebar's files, canvas, board, and background tasks.
---

# Projects & the sidebar

The left sidebar holds your chats and projects. The right-hand sidebar shows
what the agent is working with in the current chat: its files, its canvas, its
goals and tasks, and anything running in the background.

## Projects

A project groups related chats. Every chat in a project shares:

- **One workspace folder.** Files the agent writes in one chat are there for
  the next. Other projects can't see them. See
  [Workspace & sandbox](../03-features/filesystem.md#where-files-go) for where
  the folder lives on your computer.
- **Project context.** A short note about the project that every chat in it
  reads, kept in the workspace as `context.md`. The agent keeps it up to date,
  and you can edit it yourself (see [Context](#context)).
- **A board** of the project's tasks and goals (see [Board](#goal-and-board)).

New chats go to **Home**, the default project. Chats that arrive from
[chat apps](../05-chat-apps/README.md) go to **Social**. These two projects
can't be deleted.

### Creating and moving

- **New project:** in the sidebar's **Projects** list, click **+** and type a
  name. You can also pick or create a project on the new-chat screen, next to
  **Creating in**.
- **Move to project:** open a chat's **Actions** menu (⋯) and choose the
  project.
- **Rename** or **Delete** a project from its own menu. Deleting a project that
  still has chats moves them to **Home** first.

## Organizing the chat list

| To | Do this |
|---|---|
| Start a chat | Click **New chat** at the top of the list. |
| Find a chat | Type in **Search chats...**. It matches chat titles and message text. |
| Keep a chat at the top | Choose **Pin chat** in its **Actions** menu. It moves to **Pinned**. |
| Rename or delete a chat | Use its **Actions** menu. |
| Switch layout | Open **Organize** (⋯ next to the list's heading) and pick **By project** or **Single list**. |

Small labels on a chat tell you more at a glance: **Running** while the agent
is working, an unread count, **Heartbeat** for check-in chats, how many
sub-agents it started, and **Branched from** for a copy made with
[Branch from here](./chat.md#branch-from-here).

### Tasks

When you have scheduled tasks or heartbeats, a **Tasks** section lists them
with their next run time, or with an error if the last run failed. Click one to
open its chat. **View all N scheduled tasks** opens **Settings → Automation**.
Deleting a task from its menu removes the task; a task that runs in its own
chat loses that chat too. See [Automation](../03-features/automation.md).

## The right-hand sidebar

Open the right-hand sidebar from the icons along the right edge of a chat. A
dot on an icon means it has something new.

| Tab | What it shows |
|---|---|
| **Files** | The agent's files. |
| **Context** | The project context and any repository instructions. |
| **Web** | The agent's searches, the pages it read, and a live view of its browser. |
| **Canvas** | Interactive panels the agent shows you. |
| **Background tasks** | Commands and sub-agents running in the background. |
| **Goal** | This chat's goal and tasks, and the way into the project's board. |
| **Tools** | Which tools this chat may use. See [Tools](../03-features/tools/tools.md). |

### Files

Switch between three folders: **Workspace** (this project's folder),
**Shared** (shared by every project), and **Mounts** (folders you've mounted,
for example with **Working Dir**). Click a file to preview it; clicking a file
mentioned in the chat opens it here too.

- **Upload file** adds a file to the top of **Workspace** or **Shared**.
- **Open in Explorer** opens the folder on your computer.
- Right-click a file or folder for **Open**, **Reveal in file manager**,
  **Copy path**, and **Delete**. Deleting can't be undone.

In **Mounts**, you can browse and open files, but **Upload file**, **Open in
Explorer**, and **Delete** aren't available.

### Context

The **Context** tab shows the note the agent keeps about this project under
**Project context**. Click **Edit** to change it. The same note appears in the
**Memory** view, under **Project context**, for every project that has one.

When the chat is working in a folder that has `AGENTS.md` or `CLAUDE.md`
instruction files, they're listed under **Repository instructions**. If there
are several, the one closest to the working folder wins.

### Web

See [Watching what the agent does](../03-features/tools/browser.md#watching-what-the-agent-does).

### Canvas

When the agent shows you something interactive, such as a table, a form, or a
set of buttons, it appears here. What you click or fill in goes straight back
to the agent.

### Background tasks

Long-running commands and sub-agents appear here. Open one to follow its
output, see how it ended, **Stop** it, or redirect a sub-agent. See
[Tools](../03-features/tools/tools.md) for how background commands and
[sub-agents](../03-features/tools/tools.md#sub-agents) work.

### Goal and board

The **Goal** tab shows the chat's **Active Goal** with **Pause**, **Resume**,
and **Clear** buttons, followed by the tasks assigned to this chat. See
[Goal mode](../03-features/automation.md#goal-mode).

Below them, **Open Board** opens the **Project Board**: every task in the
project, from every chat, in three columns (to do, active, done), with the
project's goals along the top. On the board you can add a task, move a task to
the next column, or delete it.
