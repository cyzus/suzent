---
sidebar_position: 1
title: 模型与提供商
description: 连接 OpenAI、Anthropic、Gemini、Ollama 等模型提供商，或你自己运行的模型。
---

# 模型与提供商

**主权心智。** 模型是引擎，不是自我。智能体的身份存在于它的记忆、技能和工作区中，所以你可以更换提供商，或同时使用多个提供商，而不必从头开始。请见[什么才是主权智能体？](https://suzent.com/sovereign)。

Suzent 支持所有主流模型提供商，也支持你自己运行的模型。想添加多少就添加多少，并在聊天窗口的模型选择器中为每个对话挑选模型。

## 添加提供商

1. 打开 **设置 → 提供商**，点击你要配置的提供商。
2. 在 **API 密钥** 标签页点击 **修改**，粘贴你的密钥。
3. 在 **模型** 标签页点击 **获取**。这一步会验证密钥并加载可用模型。
4. 勾选需要的模型，然后点击 **保存更改**。

密钥保存在你电脑上 Suzent 的本地数据库中，绝不会以明文写入配置文件。

<a id="supported-providers"></a>

## 支持的提供商

| 提供商 | 你需要 |
|---|---|
| [OpenAI](./cloud/openai.md) | API 密钥。也支持 Azure OpenAI 和兼容接口。 |
| [ChatGPT 订阅](./cloud/chatgpt-subscription.md) | 你的 ChatGPT 账号，无需 API 密钥。 |
| [Anthropic](./cloud/anthropic.md) | API 密钥。 |
| [Google Gemini](./cloud/gemini.md) | API 密钥，有免费额度。 |
| [xAI（Grok）](./cloud/xai.md) | API 密钥。 |
| [DeepSeek](./cloud/deepseek.md) | API 密钥。 |
| [DashScope（阿里云百炼）](./cloud/dashscope.md) | API 密钥，用于通义千问模型。 |
| [Moonshot（Kimi）](./cloud/moonshot.md) | API 密钥。 |
| [智谱 AI（GLM）](./cloud/zhipu.md) | API 密钥。 |
| [MiniMax](./cloud/minimax.md) | API 密钥。 |
| [小米 MiMo](./cloud/xiaomi-mimo.md) | API 密钥。 |
| [OpenRouter](./cloud/openrouter.md) | 一个密钥即可使用数百个模型。 |
| [LiteLLM Proxy](./local/litellm.md) | 你自己的 LiteLLM 代理。 |
| [Ollama](./local/ollama.md) | 在你电脑上运行的 Ollama，无需密钥。 |
| [vLLM](./local/vllm.md) | 你自己的 vLLM 服务。 |
| [SGLang](./local/sglang.md) | 你自己的 SGLang 服务。 |

有了模型之后，在[模型角色](./model-roles.md)中决定每项工作由哪个模型负责。

## 小贴士

**环境变量。** 你可以在启动 Suzent 前设置 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 等环境变量。它们会在设置中显示为"来自环境变量"，无法在应用里修改。每个提供商的页面都列出了对应的变量。

**自定义模型。** 如果列表里没有你想要的模型，可以在提供商卡片中添加模型 ID，例如 `openai/gpt-4o-2024-11-20`。

**模型信息。** Suzent 会记录每个模型的上下文窗口、价格，以及是否支持图片和工具调用。点击 **获取** 时会自动更新，通常你完全不需要操心。
