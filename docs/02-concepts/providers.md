---
sidebar_position: 1
title: Models & Providers
description: Connect OpenAI, Anthropic, Gemini, Ollama, and other model providers, and choose which model handles which job.
---

# Models & Providers

**Sovereign mind.** The model is an engine, not the self. Your agent's identity
lives in its memory, skills, and workspace, so you can switch providers, or run
several at once, without starting over. See
[what makes an agent sovereign](https://suzent.com/sovereign).

Suzent works with any major model provider. Add as many as you like and pick a
model per conversation from the model selector in the chat window.

## Add a provider

1. Open **Settings → Providers** and click the provider you want.
2. On the **API KEYS** tab, click **CHANGE** and paste your key.
3. On the **MODELS** tab, click **FETCH**. This checks the key and loads the
   models it can use.
4. Tick the models you want, then click **Save Changes**.

Keys are stored in Suzent's local database on your machine, never in plain-text
config files.

## Supported providers

| Provider | Where to get a key | Notes |
|---|---|---|
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | Keys start with `sk-`. An optional base URL works for Azure OpenAI and compatible proxies. |
| ChatGPT Subscription | No key needed | Sign in with your ChatGPT account. See [below](#chatgpt-subscription). |
| Anthropic | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | Claude models. Keys start with `sk-ant-`. |
| Google Gemini | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) | Free tier available. Keys start with `AIza`. |
| xAI (Grok) | [console.x.ai](https://console.x.ai) | Keys start with `xai-`. |
| DeepSeek | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) | Low cost, includes a reasoning model. |
| DashScope (Alibaba Cloud) | [bailian.console.aliyun.com](https://bailian.console.aliyun.com) | Qwen models. |
| Moonshot (Kimi) | [platform.moonshot.cn](https://platform.moonshot.cn) | Long context. |
| Zhipu AI (GLM) | [open.bigmodel.cn](https://open.bigmodel.cn) | GLM models. |
| MiniMax | [platform.minimaxi.com](https://platform.minimaxi.com) | |
| Xiaomi MiMo | Xiaomi MiMo console | OpenAI-compatible API. |
| OpenRouter | [openrouter.ai/keys](https://openrouter.ai/keys) | Hundreds of models from one key. |
| LiteLLM Proxy | Your own proxy | Enter the proxy URL and master key. Useful for teams and cost tracking. |
| Ollama | No key needed | Runs models on your own machine. See [below](#ollama). |

### ChatGPT Subscription

Use the models included with your ChatGPT plan instead of paying for API usage.

1. Open **Settings → Providers → ChatGPT Subscription** and click **Sign in**.
2. Open the link shown, enter the code, and approve.
3. Back in Suzent, enable the `chatgpt/...` models you want.

If sign-in expires, disconnect and sign in again from the same card.

### Ollama

Ollama runs models entirely on your computer, with no API key and no internet
connection.

1. Install Ollama from [ollama.com](https://ollama.com) and pull a model:

   ```bash
   ollama pull llama3.2
   ```

2. Open the Ollama card in **Settings → Providers** and click **FETCH** to
   list your local models. Change the base URL only if Ollama is not running at
   `http://localhost:11434`.

## Model roles

Not every job needs your biggest model. **Settings → Model Roles** lets you
assign a model to each kind of work:

| Role | Used for |
|---|---|
| **Primary** | Your conversations. Needs tool use and a large context window. |
| **Cheap** | Lightweight background jobs: chat titles, picking out facts to remember, and quick decisions such as whether a goal is done or a tool call is safe. A small, fast model is ideal. |
| **Dream** | Overnight [memory consolidation](./memory/README.md#how-memory-is-tidied). |
| **Vision** | Reading images. Uses a vision-capable Primary model when left empty. |
| **Embedding** | Memory search. |
| **Image Generation, Image Editing, Video generation, TTS** | The [creative tools](./tools/tools.md#images-video-and-speech). |

Leave a task role empty and it inherits from its parent: chat titles use Cheap,
and Cheap uses Primary. Embedding and the creative roles have no parent, so
assign a model before using them. Each role can also hold backup models that
are tried in order if the first one fails.

## Tips

**Environment variables.** You can set keys such as `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` in your environment before starting Suzent. They show up in
Settings as **Set in env** and cannot be changed from the app.

**Custom models.** If a model you want is missing from the list, add its ID
under **Custom Models** on the provider card, for example
`openai/gpt-4o-2024-11-20`.

**Model details.** Suzent keeps track of each model's context window, pricing,
and whether it can see images or call tools. It updates this automatically when
you click **FETCH**, so you normally never need to think about it.
