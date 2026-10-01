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

### Use the installer

Download the installer for your platform from the [landing page](/#download). On macOS, choose Apple Silicon for M-series Macs or Intel for Intel-based Macs. Windows and Linux downloads target x86_64.

On Windows, open the downloaded `.exe`. On macOS or Linux, open Terminal in your download folder and run the following, replacing `<filename>` with the downloaded installer's exact name:

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

### Mainland China Mirror Mode

If package downloads are slow from mainland China, enable mirror mode before running setup:

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
$env:SUZENT_CHINA_MIRROR="1"; powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | SUZENT_CHINA_MIRROR=1 bash
```

</TabItem>
</Tabs>

Mirror mode configures PyPI, npm, Playwright, Node via nvm, and Rustup mirrors. If GitHub itself is slow, set `SUZENT_REPO_URL` or `SUZENT_RELEASE_BASE_URL` to a mirror you trust before running setup.

---

## 2. Launch

```bash
suzent start
```

This starts the backend and opens the desktop interface.

---

## 3. Add Your Model Provider

Once the UI is open, go to **Settings → Providers** to configure your API key. The most common starting points:

<Tabs groupId="provider">
<TabItem value="openai" label="OpenAI" default>

**Get your key:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Create new secret key (starts with `sk-...`)

In Settings, open the OpenAI card → **API KEYS** tab → **CHANGE** → paste your key. Then go to the **MODELS** tab → **FETCH**, select the models you want, and click **Save Changes**.

</TabItem>
<TabItem value="anthropic" label="Anthropic">

**Get your key:** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → Create Key (starts with `sk-ant-...`)

In Settings, open the Anthropic card → **API KEYS** tab → **CHANGE** → paste your key. Then go to the **MODELS** tab → **FETCH**, select the models you want, and click **Save Changes**.

</TabItem>
<TabItem value="gemini" label="Google Gemini">

**Get your key (free tier available):** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → Create API Key (starts with `AIza...`)

In Settings, open the Google Gemini card → **API KEYS** tab → **CHANGE** → paste your key. Then go to the **MODELS** tab → **FETCH**, select the models you want, and click **Save Changes**.

</TabItem>
</Tabs>

Using DeepSeek, Grok, OpenRouter, Ollama, your ChatGPT subscription, or another provider? See [Models & Providers](../04-models/README.md).

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

**Port conflict on startup** — `suzent start` detects conflicts and asks if you want to kill blocking processes. Type `y` to proceed.

**Updating** — Run `suzent update`, or see [Updating Suzent](./updating.md).

---

## Next Steps

- [Models & Providers](../04-models/README.md): add more models and choose which one does what
- [Memory](../03-features/memory/README.md): what your agent remembers and how to edit it
- [Tools](../03-features/tools/tools.md): everything your agent can do
- [Chat apps](../05-chat-apps/README.md): talk to it from Telegram, Slack, and more
- [Automation](../03-features/automation.md): schedule tasks and check-ins
