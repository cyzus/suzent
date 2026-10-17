---
sidebar_position: 8
title: Tasks & planning
description: How the agent breaks work into tracked tasks, how to follow project progress, and how it schedules its own follow-ups.
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

## Follow task progress

The task panel shows this conversation's goal, current steps, and anything
waiting for your input. This conversation uses a checklist in creation order,
with checked, struck-through completed steps kept visible. Status markers are
updated by the agent. Goal details separate
the execution turn budget from the number of completed steps.

Select **Entire project** at the top of the task panel to follow work across chats.
Select **This conversation** to focus on the current chat and its goal. Drag the
panel wider for the full list, or drag it narrower to keep it beside
the conversation. Resizing keeps your scope and expanded groups.
The project list puts tasks needing your attention first, followed by work in
progress, other waiting tasks, and to-dos. The same list adapts to the panel width.
Completed tasks are collapsed in the project list; cancelled tasks are hidden in both scopes.

Click a task to open its conversation. Waiting tasks explain what is needed
next when the agent has recorded that information. Completed tasks can include
an outcome summary. Open the conversation to review the full result.

To start new work, describe it in the conversation and send your message.
Tasks without a linked conversation are shown as information only; clicking
them does not start a new conversation or execute the task. The agent maintains task states as it works. To abandon a
task, tell the agent in the conversation rather than moving cards yourself.

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
