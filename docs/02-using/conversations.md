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
- **Archive what's finished.** Right-click a chat (or a selection of chats)
  and choose **Archive chat** to clear it out of the sidebar without deleting
  it. Archived chats collect under **Archived** at the bottom of the sidebar
  and still show up in search; choose **Unarchive chat** to bring one back.
  The mobile app doesn't list archived chats.
- **Tell it what you know.** Mention constraints, preferences, and where things
  are. What it learns about you is kept in [memory](../03-features/memory/README.md),
  so you don't have to repeat yourself next time.
- **Bigger jobs can run on their own.** For work that takes many steps, set a
  goal with `/goal` and the agent keeps working until it's met. For work that
  should repeat, schedule it. See [Automation](../03-features/automation.md).
- **Take the suggested reply.** After each answer, a guess at your next
  message may appear in grey in the chat box. Press **Tab** or **→** to accept
  it, keep typing to ignore it, or press **Esc** to hide it. The guess is saved
  with the chat, so it's still there when you reopen the chat, restart the app
  or open it on another device, until the conversation moves on. Turn it off
  by opening the **Input Suggestion** row in **Settings → Model Roles**.

## Give it the right material

The agent only sees what you give it.

| You want it to use | Do this |
|---|---|
| A document or image you have | Attach it, or paste the image into the message. It's kept in the project's folder. |
| A file it can already reach | Type `@` and part of the file name to point at it exactly. |
| Another conversation | Type `@`, choose **Chats**, and select a conversation. Suzent receives its title and reference, then reads its messages only when needed. |
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
and press Enter to send it as a **Redirect**: the agent keeps what it has done
so far and continues with your correction.

If it isn't a correction, just the next thing to do, press Cmd+Enter (Ctrl+Enter
on Windows and Linux) instead. The message waits under **Queued messages** and
is sent when the turn ends. You can cancel it, or click **Steer** to send it
right away as a redirect. You can redirect or stop a single sub-agent the
same way, from its box in the chat.

## Find what it made

What the agent delivered in a chat is collected under **Artifacts** in the side
panel: images it generated or edited, videos and speech it made, files it sent
you, and files it saved into the project library's `artifacts/` folder. Newest
comes first, and a file saved several times is listed once. Images show as
thumbnails you can open full size, videos and audio play right in the panel,
and clicking a file opens it under **Files**. Above a file open there, the
folder button shows it in Finder or File Explorer, and the clipboard button
copies where it is saved on your computer.

Ordinary edits, such as code or notes it changed while working, stay on the
**Edited files** card under each reply instead. Files it only read are not
listed, and neither are changes you undid. The **Overview** shows how many
artifacts there are and the latest few images.

To see everything it has made across all your chats, click **Artifacts** in the
left sidebar. Files are grouped by project, so pick a project on the left to see
only its files, or filter to images, video and audio, or other files, and search
by file name or chat title. Each file shows the chat that made it; click the chat
name to jump back to that conversation. Files you put in a project's
`artifacts/` folder yourself show up too, marked as in the project library.

## Talk instead of typing

When the message box is empty, its send button shows a microphone. Click it to
start voice mode, and just speak. As soon as you type, it turns back into the
send button. A fast voice model answers you out loud and hands
anything that needs real work to your agent, which does it in the chat as
usual, with its tools, memory, and the chat's permission mode. While it works
you can keep talking: add to the request, correct it, or say "stop". When it's
done, the voice reads you a short summary and leaves code, links, and long
lists in the chat. Click the **✕** on the voice bar to end the call; switching
to another chat ends it too.

Voice mode needs an OpenAI, Google Gemini, xAI, or DashScope (Qwen) API key. Under
**Settings → Voice & audio → Realtime voice** you can pick the model, its
voice, and how sensitive it is to speech. If Suzent hears its own voice from
your speakers, set sensitivity to **Low** (Gemini only), or use headphones.

### Start voice mode without clicking

Under **Settings → Voice & audio → Hands-free start**:

- **Wake word.** Turn it on and Suzent listens for a phrase such as
  "你好 Suzent" or "Hey Suzent", then starts voice mode in the chat you have
  open. The listening happens on your computer with a small offline model;
  no audio leaves it until voice mode starts. While it is listening, the
  empty message box reads "Type, or say …" with your phrase; if it can't
  listen, a line under the message box says why. The first time you turn it on, Suzent installs the Wake
  word plugin and downloads its model (about 25 MB together). Type a phrase
  and press Enter to add it, up to 8; phrases can be Chinese, English, or
  mixed. If an English word has no known pronunciation, its phrase turns red.
  Raise the sensitivity if it misses you, lower it if it wakes by mistake. It
  listens only while Suzent is open, and only while the Wake word plugin is
  installed: removing it under **Settings → Plugins** stops the listening.
- **Voice shortcut** (desktop app). Click the box and press a key combination,
  such as Ctrl+Shift+Space (⌘⇧Space on a Mac), to start or end voice mode from
  any app. **Remove** turns it off. Hovering the microphone button reminds you
  of the shortcut and the wake phrase.

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
