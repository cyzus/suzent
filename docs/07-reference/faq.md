---
sidebar_position: 5
title: FAQ & troubleshooting
description: Answers to the questions new users ask most, from API keys and costs to backups, logs, and bots that don't reply.
---

# FAQ & troubleshooting

## Getting started

### I don't have an API key. Can I still use Suzent?

Yes. [Ollama](../04-models/local/ollama.md) runs models on your own computer
with no key and no internet connection. Google Gemini has a
[free tier](../04-models/cloud/gemini.md), and the
[ChatGPT subscription](../04-models/cloud/chatgpt-subscription.md) provider
signs in with your ChatGPT account instead of a key.

### The terminal says "command not found: suzent".

Close and reopen your terminal after installing. If it still fails, check the
setup script's output for how to add Suzent to your `PATH`. See the
[Quickstart](../01-getting-started/quickstart.md#troubleshooting).

### Suzent won't start because the port is in use.

Suzent uses port `25314`. If an older Suzent is still running, `suzent stop`
ends it. Otherwise start Suzent on another port with `suzent start --port <port>`,
or set `SUZENT_PORT`. See [Command line](./cli.md#running-suzent).

### How much am I spending?

Open **Settings → Usage** to see your spending, API calls, and tokens per day.
Type `/status` in a conversation to see that conversation's tokens and cost.

## Your data

### Where are my files?

Everything is in the `.suzent` folder in your home folder. Files the agent
keeps go to the project's library, in `~/.suzent/sandbox/projects/<project>/`.
See [The data folder](./configuration.md#the-data-folder) for the full layout.

### Is my data sent anywhere?

Suzent runs on your computer and doesn't send usage analytics. Your messages
go to the model provider you choose, and with Ollama nothing leaves your
machine. Web searches go to DuckDuckGo, or to your own SearXNG. Suzent also
checks GitHub for new releases. GitHub Sync and chat apps only send data once
you set them up.

### How do I back up Suzent, or move to a new computer?

Turn on [GitHub Sync](../03-features/github-sync.md). It keeps your settings,
skills, and memory in a private GitHub repository you own, and brings them to
another computer. API keys are never synced, so add them again in
**Settings → Providers** on the new computer.

### How do I start over from scratch?

To empty a single conversation, type `/clear`. To reset Suzent entirely, quit
it, run `suzent service stop` if you use the background service, then rename
or move the `~/.suzent` folder. Suzent creates a new, empty one the next time
it starts. Your API keys stay in your system's keychain and are picked up again.

### The agent forgot something, or remembers something wrong.

To forget something, delete it in the **Memory** panel. To correct it, say the
corrected version in a conversation. Memory is also a set of Markdown files you
can edit yourself. See
[Managing what's remembered](../03-features/memory/README.md#managing-whats-remembered).

## Using the agent

### The agent can't see my folder.

The agent only reaches its project library, the shared folder, and folders you mount. Click
**Working Dir** in the chat box and choose the folder. See
[Giving the agent access to your folders](../03-features/filesystem.md#giving-the-agent-access-to-your-folders).

### How do I undo what the agent just did?

Click the retry icon under its last reply, or type `/retry`. That rolls back
the last turn, including file edits, and runs your message again. `/undo` only
reverts the file edits. See [Slash commands](./slash-commands.md#undo-and-retry).

### Can I stop the agent asking for permission all the time?

Switch the conversation to **Smart** or **Full Access** with the mode selector
next to the message box, or choose one of the
"always allow" answers when it asks. See [Permissions & approvals](../03-features/tools/human-in-the-loop.md).

### Scheduled tasks don't run when I close the window.

Tasks, heartbeats, and chat apps only work while Suzent is running. Turn on
**Settings → Background Service** to keep it running after you close the
window. See [Automation](../03-features/automation.md#keep-suzent-running-in-the-background).

## Troubleshooting

### My chat app bot doesn't reply.

Check three things. Suzent must be running, so turn on the background service
if you closed the window. The app must be enabled in
**Settings → Social Channels**. And your own user ID must be in
**Allowed users** on the **Access control** tab, because messages from anyone
else are refused. See [Access control & pairing](../05-chat-apps/access-control.md).

### The sandbox won't start.

The sandbox needs Docker. Make sure Docker Desktop (or Docker Engine on Linux)
is running, and that `docker ps` works in a terminal. To work without it, turn
the sandbox off in **Settings → Security**. See
[Using the sandbox](../03-features/filesystem.md#using-the-sandbox).

### Where are the logs?

Run `suzent logs --desktop` for the desktop app's log, and add `-f` to follow
it live. If you use the background service, its log is under
**Settings → Background Service → Service log**, and `suzent service logs`
prints where the file is. All logs are kept in `~/.suzent/runtime/`.

### Something seems broken after installing.

Run `suzent doctor` to check that the tools Suzent needs are installed. For a
background service that won't start, run `suzent service doctor`.

### How do I update?

Open **Settings → About** and click **Check for updates**, or run
`suzent update`. If an update was interrupted, run `suzent repair`. See
[Updating Suzent](../01-getting-started/updating.md).
