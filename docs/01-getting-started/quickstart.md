---
sidebar_position: 2
title: Quickstart
description: Install Suzent, connect a model, and send your first message in a few minutes.
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Quickstart

Get Suzent running in a few minutes.

---

## 1. Install

### From the Microsoft Store (Windows, recommended)

<a href="https://apps.microsoft.com/detail/9MZQ1HHXHVZT?mode=full"><img src="https://get.microsoft.com/images/en-us%20dark.svg" alt="Get it from Microsoft" width="200" /></a>

Click **Get** in the Store, then open Suzent from the Start menu. Python, Git and everything else are bundled, so there is nothing else to install. Then continue with [step 3](#3-add-your-model-provider).

How the Store build differs from the installer:

- **Updates come from the Microsoft Store.** `suzent update`, `suzent upgrade` and `suzent repair` are turned off in the Store build.
- **Your data stays in `~/.suzent`** (chats, memory, settings, API keys), the same folder the installer uses, so uninstalling the app does not delete it.
- **Start at login** (Settings → Background service) uses Windows' startup-app setting. You can also switch it off in Settings → Apps → Startup.
- **Side by side with the installer version.** You can have both installed, and they share `~/.suzent`. Don't run them at the same time, though. The Store app never attaches to a backend started by the installer version, so it starts a second backend on the same data. Quit one, including its background service, before opening the other, and turn on start at login in only one of them.

### Use the installer

Download the installer for your platform from the [landing page](/#download). The macOS installer is a universal build that runs natively on both Apple Silicon and Intel Macs. Windows and Linux downloads target x86_64.

- **macOS:** open the downloaded `.dmg`, then double-click **Suzent Installer**. You can also drag it to Applications first and open it from there.
- **Windows:** open the downloaded `.exe`.
- **Linux:** open Terminal in your download folder and run the following, replacing `<filename>` with the downloaded installer's exact name:

  ```bash
  chmod +x ./<filename>
  ./<filename>
  ```

Follow the installer to choose your workspace and set up Suzent. Internet access is required. The current release requires Git on macOS and Linux; install it first if the installer asks for it.

### Use the terminal

**Prerequisites:** [Node.js 20+](https://nodejs.org/) and [Git](https://git-scm.com/downloads).

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
```

</TabItem>
</Tabs>

The script installs Suzent and any missing dependencies (Python/uv, Rust, build tools).

### Installing from mainland China

Setup picks mirrors from the network it runs on: when Google is unreachable but the mainland mirrors answer, Suzent itself (from its Gitee mirror), Python, Python packages, the Playwright browser and uv come from mainland mirrors. There is nothing to turn on.

If `raw.githubusercontent.com` does not load, fetch the same script from jsDelivr:

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://cdn.jsdelivr.net/gh/cyzus/suzent@main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/cyzus/suzent@main/scripts/setup.sh | bash
```

</TabItem>
</Tabs>

Set `SUZENT_CHINA_MIRROR=1` or `SUZENT_CHINA_MIRROR=0` before running setup to force mirror mode on or off. If GitHub itself is slow, set `SUZENT_REPO_URL` or `SUZENT_RELEASE_BASE_URL` to a mirror you trust.

---

## 2. Launch

```bash
suzent start
```

This starts the backend and opens the desktop interface.

---

## 3. Add Your Model Provider

On a new installation with no configured model provider, the chat screen opens a setup
flow. You can also open **Setup guide** from **Settings → About**. The standalone
`/setup` page hides the application sidebars while you configure your agent:

1. Connect a provider, enable your models, and choose a default chat model.
   You can continue without a reply test. **Check connection (no generation)** checks
   model-list access when supported; it does not prove model access or quota.
   **Test model reply (optional)** sends a small text request and may incur a usage charge.
2. Review **Model roles**. Recommendations match enabled models to known
   capabilities, including vision, image generation/editing, speech synthesis,
   video, and embeddings. Unknown or missing capabilities remain unassigned;
   existing assignments are preserved. Specialist models are not invoked during
   matching. You can adjust the assignments before saving.
   Save your assignments to finish setup and open a new conversation.

Provider and role settings remain available after setup:

Once the UI is open, go to **Settings → Providers** to configure your API key. The most common starting points:

<Tabs groupId="provider">
<TabItem value="openai" label="OpenAI" default>

**Get your key:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Create new secret key (starts with `sk-...`)

In Settings, find **OpenAI** under **Add a provider** and open its card. On the **API keys** tab, paste your key and click **Save**. Then click **Test connection** and tick the models you want on the **Models** tab. Changes save on their own.

</TabItem>
<TabItem value="anthropic" label="Anthropic">

**Get your key:** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → Create Key (starts with `sk-ant-...`)

In Settings, find **Anthropic** under **Add a provider** and open its card. On the **API keys** tab, paste your key and click **Save**. Then click **Test connection** and tick the models you want on the **Models** tab. Changes save on their own.

</TabItem>
<TabItem value="gemini" label="Google Gemini">

**Get your key (free tier available):** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → Create API Key (starts with `AIza...`)

In Settings, find **Google Gemini** under **Add a provider** and open its card. On the **API keys** tab, paste your key and click **Save**. Then click **Test connection** and tick the models you want on the **Models** tab. Changes save on their own.

</TabItem>
</Tabs>

Using DeepSeek, Qwen, Kimi, GLM, a coding plan, OpenRouter, Ollama, your ChatGPT subscription, or another provider? See [Models & Providers](../04-models/README.md).

---

## 4. Start Chatting

Pick a model from the model selector in the chat window and send your first message.

**That's it.** Your agent has memory, tools, and automation ready out of the box.
Try asking it to remember something about you, or to research a topic and
write a short summary to a file.

---

## Troubleshooting

**"Command not found: suzent"** — Restart your terminal after installation. If it still fails, check the setup script output for how to manually add the scripts folder to your PATH.

**"System Health Check Failed"**

```bash
suzent doctor
```

**Port conflict on startup** — `suzent start` stops if the port is already in use and tells you which process holds it. Usually that's another copy of Suzent: run `suzent stop`, or start on another port with `suzent start --port <port>`.

**Updating** — Run `suzent update`, or see [Updating Suzent](./updating.md).

More answers are in [FAQ & troubleshooting](../07-reference/faq.md).

---

## Next Steps

- [Working with your agent](../02-using/conversations.md): hand it tasks, steer it, and undo what went wrong
- [Making it yours](../02-using/make-it-yours.md): what to set up next
- [Desktop, phone, and browser](./platforms.md): reach your agent from your phone or another computer
- [Models & Providers](../04-models/README.md): add more models and choose which one does what
- [Memory](../03-features/memory/README.md): what your agent remembers and how to edit it
- [Tools](../03-features/tools/README.md): everything your agent can do
- [Chat apps](../05-chat-apps/README.md): talk to it from Telegram, Slack, and more
- [Automation](../03-features/automation.md): schedule tasks and check-ins
