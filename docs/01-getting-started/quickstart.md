---
sidebar_position: 2
title: Quickstart
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# Quickstart

Get Suzent running in under 5 minutes.

---

## 1. Install

**Prerequisites:** [Node.js 20+](https://nodejs.org/) and [Git](https://git-scm.com/downloads).

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
powershell -c "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
```

</TabItem>
</Tabs>

The script installs Suzent and any missing dependencies (Python/uv, Rust, build tools).

---

## 2. Launch

```bash
suzent start
```

This starts the backend and opens the UI in your browser. The default address is **http://localhost:25315**.

---

## 3. Add Your Model Provider

Once the UI is open, go to **Settings → Providers** to configure your API key. The most common starting points:

<Tabs groupId="provider">
<TabItem value="openai" label="OpenAI" default>

**Get your key:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → Create new secret key (starts with `sk-...`)

In Settings, paste it into **OpenAI → API Key**, enable the models you want, then click **Save → Verify**.

</TabItem>
<TabItem value="anthropic" label="Anthropic">

**Get your key:** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → Create Key (starts with `sk-ant-...`)

In Settings, paste it into **Anthropic → API Key**, enable the models you want, then click **Save → Verify**.

</TabItem>
<TabItem value="gemini" label="Google Gemini">

**Get your key (free tier available):** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → Create API Key (starts with `AIza...`)

In Settings, paste it into **Google Gemini → API Key**, enable the models you want, then click **Save → Verify**.

</TabItem>
</Tabs>

Using DeepSeek, Grok, OpenRouter, Ollama, or another provider? See the full [Providers reference](../concepts/providers).

---

## 4. Start Chatting

Pick a model from the model selector in the chat window and send your first message.

**That's it.** Your agent has memory, tools, and automation ready out of the box.

---

## Troubleshooting

**"Command not found: suzent"** — Restart your terminal after installation. If it still fails, check the setup script output for how to manually add the scripts folder to your PATH.

**"System Health Check Failed"**

```bash
suzent doctor
```

**Port conflict on startup** — `suzent start` detects conflicts and asks if you want to kill blocking processes. Type `y` to proceed.

**Updating**

```bash
suzent upgrade
```

---

## Next Steps

- [What is Suzent?](./intro) — Understand the architecture
- [Providers](../concepts/providers) — Full list of supported models and providers
- [Tools](../concepts/tools) — See everything your agent can do
- [Memory](../concepts/memory) — How persistent memory works
- [Automation](../concepts/automation) — Schedule tasks and set up heartbeat monitors
