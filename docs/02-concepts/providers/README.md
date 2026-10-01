---
sidebar_position: 1
title: Models & Providers
description: Connect OpenAI, Anthropic, Gemini, Ollama, and other model providers, or models you run yourself.
---

# Models & Providers

**Sovereign mind.** The model is an engine, not the self. Your agent's identity
lives in its memory, skills, and workspace, so you can switch providers, or run
several at once, without starting over. See
[what makes an agent sovereign](https://suzent.com/sovereign).

Suzent works with every major model provider, and with models you run
yourself. Add as many as you like and pick a model per conversation from the
model selector in the chat window.

## Add a provider

1. Open **Settings → Providers** and click the provider you want.
2. On the **API KEYS** tab, click **CHANGE** and paste your key.
3. On the **MODELS** tab, click **FETCH**. This checks the key and loads the
   models it can use.
4. Tick the models you want, then click **Save Changes**.

Keys are stored in Suzent's local database on your machine, never in plain-text
config files.

## Supported providers

| Provider | What you need |
|---|---|
| [OpenAI](./openai.md) | API key. Also works with Azure OpenAI and compatible endpoints. |
| [ChatGPT Subscription](./chatgpt-subscription.md) | Your ChatGPT account, no API key. |
| [Anthropic](./anthropic.md) | API key. |
| [Google Gemini](./gemini.md) | API key, with a free tier. |
| [xAI (Grok)](./xai.md) | API key. |
| [DeepSeek](./deepseek.md) | API key. |
| [DashScope (Alibaba Cloud)](./dashscope.md) | API key, for Qwen models. |
| [Moonshot (Kimi)](./moonshot.md) | API key. |
| [Zhipu AI (GLM)](./zhipu.md) | API key. |
| [MiniMax](./minimax.md) | API key. |
| [Xiaomi MiMo](./xiaomi-mimo.md) | API key. |
| [OpenRouter](./openrouter.md) | One key for hundreds of models. |
| [LiteLLM Proxy](./litellm.md) | Your own LiteLLM proxy. |
| [Ollama](./ollama.md) | Ollama on your computer, no key. |
| [vLLM](./vllm.md) | Your own vLLM server. |
| [SGLang](./sglang.md) | Your own SGLang server. |

Once you have models, decide which one does which job in
[Model roles](./model-roles.md).

## Tips

**Environment variables.** You can set keys such as `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` in your environment before starting Suzent. They show up in
Settings as **Set in env** and cannot be changed from the app. Each provider's
page lists its variable.

**Custom models.** If a model you want is missing from the list, add its ID
under **Custom Models** on the provider card, for example
`openai/gpt-4o-2024-11-20`.

**Model details.** Suzent keeps track of each model's context window, pricing,
and whether it can see images or call tools. It updates this automatically when
you click **FETCH**, so you normally never need to think about it.
