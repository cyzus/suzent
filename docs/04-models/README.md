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

1. Open **Settings → Providers**. Providers you have already set up are listed
   at the top; the rest wait under **Add a provider**, grouped into model
   vendors, China vendors and coding plans, relays and subscriptions, and local
   runtimes. Type a name in the search box to find one quickly.
2. Click a provider to open its card. If it offers a **Region** or **Plan**
   choice, pick the one your key belongs to.
3. On the **API keys** tab, paste your key and click **Save**. **Get a … API
   key** links to the page where you create one.
4. Click **Test connection & fetch models**. This checks the key and loads the
   models it can use.
5. Tick the models you want on the **Models** tab.

Changes save on their own. Keys are stored in your operating system's keychain
(or, where there is none, an encrypted file on your computer), never in
plain-text config files.

## Supported providers

**Model vendors**

| Provider | What you need |
|---|---|
| [OpenAI](./cloud/openai.md) | API key. Also works with Azure OpenAI and compatible endpoints. |
| [ChatGPT Subscription](./cloud/chatgpt-subscription.md) | Your ChatGPT account, no API key. |
| [Anthropic](./cloud/anthropic.md) | API key. |
| [Google Gemini](./cloud/gemini.md) | API key, with a free tier. |
| [xAI (Grok)](./cloud/xai.md) | API key. |

**China vendors and coding plans**

| Provider | What you need |
|---|---|
| [Qwen (DashScope)](./cloud/dashscope.md) | Pay-as-you-go Alibaba Cloud key, China or International. |
| [DeepSeek](./cloud/deepseek.md) | API key. |
| [MiniMax](./cloud/minimax.md) | API key, China or Global. |
| [Kimi (Moonshot)](./cloud/moonshot.md) | API key, China or Global. |
| [Kimi Code](./cloud/kimi-code.md) | Kimi Code subscription key. |
| [Zhipu GLM / Z.ai](./cloud/zhipu.md) | API key, pay as you go or GLM Coding Plan. |
| [Xiaomi MiMo](./cloud/xiaomi-mimo.md) | API key, pay as you go or Token Plan. |
| [Bailian Plan](./cloud/bailian-plan.md) | Alibaba Cloud Token Plan or Coding Plan key. |
| [Tencent Cloud](./cloud/tencent.md) | Token Plan, Coding Plan, or pay-as-you-go key. |
| [Volcengine Ark](./cloud/volcengine.md) | Coding Plan, Agent Plan, or pay-as-you-go key. |
| [StepFun](./cloud/stepfun.md) | Step Plan or pay-as-you-go key. |
| [Baidu Qianfan](./cloud/qianfan.md) | Token Plan or pay-as-you-go key. |
| [Huawei Cloud MaaS](./cloud/huaweicloud.md) | Token Plan or pay-as-you-go key. |

**Relays and subscriptions**

| Provider | What you need |
|---|---|
| [OpenRouter](./cloud/openrouter.md) | One key for hundreds of models. |
| [OpenCode Go](./cloud/opencode-go.md) | OpenCode Go subscription key. |
| [ClinePass](./cloud/clinepass.md) | ClinePass subscription key. |
| [Ollama Cloud](./cloud/ollama-cloud.md) | ollama.com API key. |
| [LiteLLM Proxy](./local/litellm.md) | Your own LiteLLM proxy. |

**Local and self-hosted**

| Provider | What you need |
|---|---|
| [Ollama](./local/ollama.md) | Ollama on your computer, no key. |
| [vLLM](./local/vllm.md) | Your own vLLM server. |
| [SGLang](./local/sglang.md) | Your own SGLang server. |

## Custom endpoint

Anything that speaks the OpenAI or Anthropic API, such as a relay or a
self-hosted gateway, can be added even if it isn't listed. At the end of
**Add a provider**, click **Custom endpoint** and fill in:

- **Name**, shown on the provider's card.
- **Protocol**: **OpenAI compatible** or **Anthropic compatible**.
- **Base URL**. For OpenAI compatible endpoints it usually ends in `/v1`;
  Suzent adds `/chat/completions`. For Anthropic compatible ones, leave off
  `/v1/messages`; Suzent adds it.
- **API Key**, or leave it empty if the endpoint needs none.

Click **Add Provider**. The new provider gets its own card, where you can
change the key and Base URL later, fetch its models, or remove it with
**Remove provider**.

Once you have models, decide which one does which job in
[Model roles](./model-roles.md).

## Tips

**Environment variables.** You can set keys such as `OPENAI_API_KEY` or
`ANTHROPIC_API_KEY` in your environment before starting Suzent. Settings marks
them **Environment**; a key you save in the app takes priority. Each provider's
page lists its variables.

**Custom models.** If a model you want is missing from the list, add its ID
in the **Add model ID...** box on the provider's **Models** tab, for example
`openai/gpt-4o-2024-11-20`.

**Model details.** Suzent keeps track of each model's context window, pricing,
and whether it can see images or call tools. It updates this automatically when
you fetch models, so you normally never need to think about it.
