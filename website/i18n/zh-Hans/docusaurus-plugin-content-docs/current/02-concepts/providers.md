---
sidebar_position: 1
title: 模型与提供商
description: 连接 OpenAI、Anthropic、Gemini、Ollama 等模型提供商，并决定每项工作由哪个模型负责。
---

# 模型与提供商

**主权心智。** 模型是引擎，不是自我。智能体的身份存在于它的记忆、技能和工作区中，所以你可以更换提供商，或同时使用多个提供商，而不必从头开始。请见[什么才是主权智能体？](https://suzent.com/sovereign)。

Suzent 支持所有主流模型提供商。想添加多少就添加多少，并在聊天窗口的模型选择器中为每个对话挑选模型。

## 添加提供商

1. 打开 **设置 → 提供商**，点击你要配置的提供商。
2. 在 **API 密钥** 标签页点击 **修改**，粘贴你的密钥。
3. 在 **模型** 标签页点击 **获取**。这一步会验证密钥并加载可用模型。
4. 勾选需要的模型，然后点击 **保存更改**。

密钥保存在你电脑上 Suzent 的本地数据库中，绝不会以明文写入配置文件。

<a id="supported-providers"></a>

## 支持的提供商

| 提供商 | 获取密钥 | 说明 |
|---|---|---|
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) | 密钥以 `sk-` 开头。可选的 Base URL 适用于 Azure OpenAI 和兼容代理。 |
| ChatGPT 订阅 | 无需密钥 | 用 ChatGPT 账号登录。见[下文](#chatgpt-subscription)。 |
| Anthropic | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) | Claude 模型。密钥以 `sk-ant-` 开头。 |
| Google Gemini | [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) | 有免费额度。密钥以 `AIza` 开头。 |
| xAI（Grok） | [console.x.ai](https://console.x.ai) | 密钥以 `xai-` 开头。 |
| DeepSeek | [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys) | 价格低，包含推理模型。 |
| DashScope（阿里云百炼） | [bailian.console.aliyun.com](https://bailian.console.aliyun.com) | 通义千问模型。 |
| Moonshot（Kimi） | [platform.moonshot.cn](https://platform.moonshot.cn) | 长上下文。 |
| 智谱 AI（GLM） | [open.bigmodel.cn](https://open.bigmodel.cn) | GLM 系列模型。 |
| MiniMax | [platform.minimaxi.com](https://platform.minimaxi.com) | |
| 小米 MiMo | 小米 MiMo 控制台 | OpenAI 兼容 API。 |
| OpenRouter | [openrouter.ai/keys](https://openrouter.ai/keys) | 一个密钥即可使用数百个模型。 |
| LiteLLM Proxy | 你自己的代理 | 填写代理地址和 master key。适合团队使用和成本统计。 |
| Ollama | 无需密钥 | 在你自己的电脑上运行模型。见[下文](#ollama)。 |

<a id="chatgpt-subscription"></a>

### ChatGPT 订阅

使用 ChatGPT 套餐中包含的模型，而不是按 API 用量付费。

1. 打开 **设置 → 提供商 → ChatGPT 订阅**，点击登录。
2. 打开显示的链接，输入验证码并确认。
3. 回到 Suzent，启用需要的 `chatgpt/...` 模型。

如果登录过期，在同一张卡片上断开连接后重新登录即可。

<a id="ollama"></a>

### Ollama

Ollama 完全在你的电脑上运行模型，不需要 API 密钥，也不需要联网。

1. 从 [ollama.com](https://ollama.com) 安装 Ollama，并拉取一个模型：

   ```bash
   ollama pull llama3.2
   ```

2. 在 **设置 → 提供商** 中打开 Ollama 卡片，点击 **获取** 列出本地模型。只有当 Ollama 不在 `http://localhost:11434` 运行时才需要修改 Base URL。

<a id="model-roles"></a>

## 模型角色

不是每项工作都需要最大的模型。**设置 → 模型角色** 让你为不同类型的工作分配模型：

| 角色 | 用途 |
|---|---|
| **主要** | 你的对话。需要支持工具调用和较大的上下文窗口。 |
| **轻量** | 轻量的后台工作：生成对话标题、挑出值得记住的事实，以及"目标是否完成""这个工具调用是否安全"之类的快速判断。小而快的模型最合适。 |
| **Dream** | 夜间的[记忆整理](./memory/README.md#how-memory-is-tidied)。 |
| **视觉** | 识别图片。留空时会使用支持视觉的主要模型。 |
| **向量嵌入** | 记忆搜索。 |
| **图像生成、图像编辑、视频生成、语音合成** | [创作类工具](./tools/tools.md#images-video-and-speech)。 |

任务角色留空时会继承上级角色：对话标题使用轻量模型，轻量模型留空时使用主要模型。向量嵌入和创作类角色没有上级，使用前需要先分配模型。每个角色还可以设置备用模型，第一个失败时按顺序尝试。

## 小贴士

**环境变量。** 你可以在启动 Suzent 前设置 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 等环境变量。它们会在设置中显示为"来自环境变量"，无法在应用里修改。

**自定义模型。** 如果列表里没有你想要的模型，可以在提供商卡片中添加模型 ID，例如 `openai/gpt-4o-2024-11-20`。

**模型信息。** Suzent 会记录每个模型的上下文窗口、价格，以及是否支持图片和工具调用。点击 **获取** 时会自动更新，通常你完全不需要操心。
