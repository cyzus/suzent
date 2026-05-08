---
sidebar_position: 1
title: Providers
---

# Providers

Suzent is model-agnostic. Configure any number of providers in **Settings → Providers** and switch between them per session.

API keys are stored in the local database — never in plain text config files.

---

## Configuring a Provider

1. Open **Settings → Providers** and click the provider card you want to configure
2. On the **API KEYS** tab, click **CHANGE** and paste your API key
3. Switch to the **MODELS** tab and click **FETCH** — this verifies the key and loads available models
4. Check the models you want to enable
5. Click **Save Changes** (bottom right of the Settings modal)

---

## Available Providers

### Cloud

| Provider | Notes |
|---|---|
| [OpenAI](./openai.md) | GPT and o-series models |
| [Anthropic](./anthropic.md) | Claude models |
| [Google Gemini](./gemini.md) | Free tier available |
| [xAI (Grok)](./xai.md) | Grok models |
| [DeepSeek](./deepseek.md) | Cost-effective; includes reasoning model |
| [MiniMax](./minimax.md) | |
| [Moonshot (Kimi)](./moonshot.md) | Long context |
| [Zhipu AI (GLM)](./zhipu.md) | GLM series |

### Aggregators & Proxies

| Provider | Notes |
|---|---|
| [OpenRouter](./openrouter.md) | 300+ models from one key |
| [LiteLLM Proxy](./litellm.md) | Self-hosted gateway |

### Local

| Provider | Notes |
|---|---|
| [Ollama](./ollama.md) | Runs entirely on your machine — no API key needed |

---

## Tips

**Environment variables** — You can set provider keys as env vars before launching Suzent instead of using the UI. The app checks the database first, then falls back to the environment. Keys set via env show up in Settings as **"Set in env"** and cannot be overwritten from the UI.

**Custom models** — For each provider you can add custom model IDs on top of the default list. In **Settings → Providers → [Provider] → Custom Models**, enter the model ID in LiteLLM format: `provider/model-name` (e.g. `openai/gpt-4o-2024-11-20`).
