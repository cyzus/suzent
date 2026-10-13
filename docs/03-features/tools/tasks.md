---
sidebar_position: 8
title: Tasks & planning
description: How the agent breaks work into tracked tasks, how the project board works, and how it schedules its own follow-ups.
---

# Tasks & planning

For bigger jobs, the agent keeps a to-do list it can't lose track of, can work
toward a goal over many turns, and can set itself reminders to come back
later. These tools are in the **Tasks & goals** group of the tool picker.
Tasks and goals are on by default; scheduling isn't, but the agent can switch
it on when it needs it.

## Tracked tasks

When a job has several steps, the agent writes them down as tasks. Each task
has a title, a description, and a status, and can depend on other tasks
("blocked by #3"). The agent marks tasks as it goes and sees the open ones at
the start of every turn, so it keeps its place even in a long conversation.

Tasks belong to the [project](../../02-using/projects.md), not just the chat.
Every chat in the project sees the same list, and each task shows which chat
it's assigned to.

## The board

The **Goal** tab in the chat's side panel shows this chat's goal and the tasks
assigned to it, with what each one blocks or is blocked by.

Click **Open Board** (or **Board**, once the chat has tasks) to see every task
in the project, from every chat, in three columns: **Todo**, **Active**, and
**Done**. On the board you can:

- add a task with **+ Add task** at the bottom of the **Todo** column;
- move a task to the next column with its arrow button, or send a finished
  task back to **Todo**;
- delete a task with its **✕** button.

The agent sees your changes on its next turn.

## Goals

A goal keeps the agent working, turn after turn, until a condition is met.
Start one with `/goal`, or ask the agent to set one. When every task in the
project is done, the agent is prompted to check whether the goal is met. See
[Goal mode](../automation.md#goal-mode) for the commands and limits.

## Follow-ups and reminders

The agent can schedule its own future turns: "The deploy is running. I'll
check back in 15 minutes." It can run something:

| Schedule | Example |
|---|---|
| Once, after a delay (at least 1 minute) | "in 20 minutes" |
| Once, at a set time | "tomorrow at 9:00" |
| Repeatedly, every 5 minutes or more | "every 30 minutes" |
| On a cron expression, no more often than every 5 minutes | "weekdays at 9:00" |

By default the follow-up runs in this conversation, so it sees the history,
and it stays quiet if it has nothing to report. The agent can instead run it
in a chat of its own, which is cheaper, and the result is announced in the
status bar.

A chat can hold at most 5 of these at once, and the agent can only change or
cancel the ones it created. They appear with your other tasks in
**Settings → Automation**, where you can switch them off or delete them. For
schedules you set up yourself, see [Automation](../automation.md#scheduled-tasks).
