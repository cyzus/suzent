---
sidebar_position: 1
title: Providers
---

# Providers

Suzent is model-agnostic. Configure any number of providers in **Settings → Providers** and switch between them per session.

API keys are stored in the local database — never in plain text config files.

---

## Configuring a Provider

1. Open **Settings → Providers**
2. Select the provider you want to add
3. Enter your credentials and click **Save**
4. Click **Verify** to confirm the connection and load available models
5. Enable the models you want to use from the model list

---

## Cloud Providers

### OpenAI

**Models:** GPT-4.1, GPT-4.1 Mini, o3, o4-mini

**Get your key:** [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

| Field | Description |
|---|---|
| `OPENAI_API_KEY` | Your API key (starts with `sk-...`) |
| `OPENAI_BASE_URL` | Optional. Override the endpoint — useful for Azure OpenAI or compatible proxies |

---

### Anthropic

**Models:** Claude Opus 4.6, Claude Sonnet 4.6, Claude Haiku 4.5

**Get your key:** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)

| Field | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Your API key (starts with `sk-ant-...`) |

---

### Google Gemini

**Models:** Gemini 2.5 Pro, Gemini 2.5 Flash, Gemini 2.0 Flash

**Get your key (free tier available):** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

| Field | Description |
|---|---|
| `GEMINI_API_KEY` | Your API key (starts with `AIza...`) |

`GOOGLE_API_KEY` is also accepted as an alias.

---

### xAI (Grok)

**Models:** Grok 3, Grok 3 Mini, Grok 3 Fast

**Get your key:** [console.x.ai](https://console.x.ai)

| Field | Description |
|---|---|
| `XAI_API_KEY` | Your API key (starts with `xai-...`) |

---

### DeepSeek

**Models:** DeepSeek V3 (Chat), DeepSeek R1 (Reasoner)

**Get your key:** [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)

| Field | Description |
|---|---|
| `DEEPSEEK_API_KEY` | Your API key (starts with `sk-...`) |

DeepSeek R1 is a reasoning model — slower but stronger for multi-step problems.

---

### MiniMax

**Models:** MiniMax M2.5, MiniMax M2.1

**Get your key:** [platform.minimaxi.com](https://platform.minimaxi.com)

| Field | Description |
|---|---|
| `MINIMAX_API_KEY` | Your API key |

---

### Moonshot (Kimi)

**Models:** Kimi v1 128K, Kimi v1 32K, Kimi v1 8K

**Get your key:** [platform.moonshot.cn](https://platform.moonshot.cn)

| Field | Description |
|---|---|
| `MOONSHOT_API_KEY` | Your API key (starts with `sk-...`) |

---

### Zhipu AI (GLM)

**Models:** GLM-4.7 Flash

**Get your key:** [open.bigmodel.cn](https://open.bigmodel.cn)

| Field | Description |
|---|---|
| `ZAI_API_KEY` | Your API key |

---

## Aggregators & Proxies

### OpenRouter

Access 300+ models from a single API key — GPT, Claude, Gemini, Mistral, Llama, and more. Useful if you want to experiment across providers without managing separate subscriptions.

**Get your key:** [openrouter.ai/keys](https://openrouter.ai/keys)

| Field | Description |
|---|---|
| `OPENROUTER_API_KEY` | Your API key (starts with `sk-or-...`) |

After saving, click **Fetch Models** to load the full catalog.

---

### LiteLLM Proxy

Run a self-hosted gateway in front of any set of models. Useful for teams, rate-limit management, or cost tracking.

**Setup:** [docs.litellm.ai](https://docs.litellm.ai)

| Field | Description |
|---|---|
| `LITELLM_MASTER_KEY` | Your proxy master key (starts with `sk-...`) |
| `LITELLM_BASE_URL` | URL of your running proxy (e.g. `http://localhost:4000`) |

Click **Fetch Models** after saving to load the models your proxy exposes.

---

## Local

### Ollama

Run models entirely on your machine — no API key or internet connection needed.

**Setup:** Install Ollama from [ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull llama3.2
```

| Field | Description |
|---|---|
| `OLLAMA_BASE_URL` | Base URL of your Ollama server (default: `http://localhost:11434`) |
| `OLLAMA_API_KEY` | Optional. Only needed if your instance requires authentication |

Click **Fetch Models** to auto-detect all locally available models.

---

## Tips

**Environment variables** — You can set provider keys as env vars before launching Suzent instead of using the UI. The app checks the database first, then falls back to the environment. Keys set via env show up in Settings as **"Set in env"** and cannot be overwritten from the UI.

**Custom models** — For each provider you can add custom model IDs on top of the default list. In **Settings → Providers → [Provider] → Custom Models**, enter the model ID in LiteLLM format: `provider/model-name` (e.g. `openai/gpt-4o-2024-11-20`).
