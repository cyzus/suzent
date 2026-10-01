---
sidebar_position: 1
title: The chat window
description: How to write to your agent, steer it while it works, and undo, retry, or branch a conversation.
---

# The chat window

The chat window is where you talk to your agent. This page walks through the
message box, what you can do while the agent is working, and how to change
course afterwards.

## Writing a message

Type in the box and press **Send**. The row of controls around the box sets up
how this chat runs.

### Choosing a model

The model picker sits next to **Send**. It lists every model you've enabled in
**Settings → Providers** (see [Models & Providers](../04-models/README.md)), and
your choice applies to the current chat only, so different chats can use
different models.

### Attaching files and images

Click the paper clip (**Attach files (images, PDFs, documents, etc.)**), drag
files onto the window (**Drop files here**), or paste an image straight into
the box. Attached files are saved in the project's uploads folder, so the agent
can open them again later (see
[Workspace & sandbox](../03-features/filesystem.md#where-files-go)).

### Pointing at a file with `@`

Type `@` followed by part of a file name to search the files the agent can
reach: its workspace, the shared folder, and any folders you've mounted. Pick a
result with the arrow keys and Enter, and the file's path is added to your
message so the agent knows exactly which file you mean.

### Working Dir

The **Working Dir** button (the folder icon) gives the agent one of your own
folders for this chat. Choose a folder, or pick one from **Recent folders**.
Click it again to see what's mounted or **Remove** a folder. See
[Giving the agent access to your folders](../03-features/filesystem.md#giving-the-agent-access-to-your-folders).

### Thinking effort

**Thinking** (under the model picker) sets how long the model reasons before it
answers. Click it to open the control, then click the mode to cycle between:

| Mode | What it does |
|---|---|
| **Auto** | Keeps the model's own default. |
| **Manual** | Drag along the bars to choose **Low**, **Med**, **High**, or **X-High**. More effort is slower but more careful. |
| **Off** | Answers without an extended reasoning pass. |

Models that can't reason ignore this setting.

### Permission mode

The selector on the left, under the box, sets how much the agent may do without
asking: **Ask permissions**, **Smart mode**, or **Full Access**. See
[Permissions & approvals](../03-features/tools/human-in-the-loop.md).

### Slash commands

Type `/` to see the available commands, such as `/goal` or `/undo`. Use the
arrow keys and Tab or Enter to pick one. The full list is in
[Slash commands](../07-reference/slash-commands.md).

## While the agent works

While a reply is being written, **Send** turns into **Stop**.

- **Stop** ends the turn.
- **Redirect.** Start typing and the button becomes **Redirect**. Sending it
  interrupts the agent, keeps what it has written so far, and continues with
  your new message. Use it to correct course without waiting for the turn to
  end.
- **Redirecting a sub-agent.** When the agent hands work to a helper, you can
  redirect the helper alone in the **Redirect this sub-agent…** field. It
  appears in the helper's box in the chat while the agent waits on it, and on
  the helper's page in the **Background tasks** sidebar. Your note is
  **Queued** and applies after the helper's current step. A **Stop** button
  next to it stops just that helper.
- **Approvals.** If the agent needs permission, it pauses and asks you right
  above the message box. See
  [Answering a request](../03-features/tools/human-in-the-loop.md#answering-a-request).

## Changing course afterwards

### Edit, rerun, or retry the last turn

Hover over your most recent message to see its buttons:

- **Edit** opens the message for changes. Click **Resend** to run it again with
  the new text. The replies below it are replaced.
- **Rerun** runs the same message again.

Under the agent's last reply, **Retry** (↺) does the same as **Rerun**. All
three roll the turn back first, including files the agent edited, then run it
again. See
[Undoing the last turn (Retry)](../03-features/filesystem.md#undoing-the-last-turn-retry).
Only the most recent turn can be edited, rerun, or retried.

### Undo file changes

When a turn edits files, a card under the reply shows **Edited N file(s)**.
Click **Diff** to see what changed, or a file name to open it. **Undo** puts
those files back as they were before that turn and leaves the conversation as
it is. If you've changed one of the files yourself since then, Suzent cancels
the undo rather than overwrite your work.

Typing `/undo` does the same for the most recent turn.

### Branch from here

To try a different direction without losing the current one, click **Branch
from here** under any reply, then **Create branch**. A new, independent
conversation starts from that point. The original conversation and your
workspace files stay unchanged. In the chat list, the copy is marked
**Branched from** the original.

Typing `/fork` makes a copy of the whole conversation.

## Finding your way in a long chat

A minimap runs down the side of the conversation, with one mark per message.
Hover a mark to preview that message, and click it to jump there.

## Chatting with Claude Code, Codex, and other agents

Instead of one of your models, a new chat can be answered by an external coding
agent such as Claude Code or Codex. In a new chat, open the model picker and
choose an agent under **ACP agents**. Only installed agents are listed; set
them up in **Settings → ACP Agents**.

A few things work differently in these chats:

- The agent is fixed once the chat starts. To use a different one, start a new
  chat.
- The agent chooses its own model and reasoning, so the **Thinking** control is
  hidden.
- When it needs permission, you see **External agent needs approval** in the
  chat.

See [Devices & other agents](../03-features/nodes.md#use-suzent-from-your-editor-acp).
