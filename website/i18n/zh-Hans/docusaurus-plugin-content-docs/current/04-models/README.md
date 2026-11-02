---
sidebar_position: 1
title: 模型与提供商
description: 连接 OpenAI、Anthropic、Gemini、Ollama 等模型提供商，或你自己运行的模型。
---

# 模型与提供商

**主权心智。** 模型是引擎，不是自我。智能体的身份存在于它的记忆、技能和工作区中，所以你可以更换提供商，或同时使用多个提供商，而不必从头开始。请见[什么才是主权智能体？](https://suzent.com/sovereign)。

Suzent 支持所有主流模型提供商，也支持你自己运行的模型。想添加多少就添加多少，并在聊天窗口的模型选择器中为每个对话挑选模型。

## 添加提供商

1. 打开 **设置 → 提供商**。已配置的提供商列在最上方，其余的都在 **添加提供商**
   里，按海外模型厂商、国内厂商与编程套餐、中转与订阅、本地与自部署分组。在搜索框里输入名称可以快速找到。
2. 点击提供商打开它的卡片。如果它有 **地域** 或 **套餐** 选项，选择你的密钥所属的那一个。
3. 在 **API 密钥** 标签页粘贴密钥，点击 **保存**。**去 … 申请 API 密钥** 链接会带你到创建密钥的页面。
4. 点击 **测试连接并获取模型**。这一步会验证密钥并加载可用模型。
5. 在 **模型** 标签页勾选需要的模型。

改动会自动保存。密钥保存在操作系统的钥匙串中（没有钥匙串时，保存在你电脑上的加密文件里），绝不会以明文写入配置文件。

<a id="supported-providers"></a>

## 支持的提供商

**海外模型厂商**

| 提供商 | 你需要 |
|---|---|
| [OpenAI](./cloud/openai.md) | API 密钥。也支持 Azure OpenAI 和兼容接口。 |
| [ChatGPT 订阅](./cloud/chatgpt-subscription.md) | 你的 ChatGPT 账号，无需 API 密钥。 |
| [Anthropic](./cloud/anthropic.md) | API 密钥。 |
| [Google Gemini](./cloud/gemini.md) | API 密钥，有免费额度。 |
| [xAI（Grok）](./cloud/xai.md) | API 密钥。 |

**国内厂商与编程套餐**

设置里的提供商名称是英文的，可以在搜索框里输入 Qwen、Kimi、Zhipu、Tencent 这样的英文名来找。

| 提供商 | 你需要 |
|---|---|
| [通义千问（DashScope）](./cloud/dashscope.md) | 阿里云按量付费密钥，国内或国际站。 |
| [DeepSeek](./cloud/deepseek.md) | API 密钥。 |
| [MiniMax](./cloud/minimax.md) | API 密钥，国内或国际站。 |
| [Kimi（Moonshot）](./cloud/moonshot.md) | API 密钥，国内或国际站。 |
| [Kimi Code](./cloud/kimi-code.md) | Kimi Code 订阅密钥。 |
| [智谱（Zhipu GLM / Z.ai）](./cloud/zhipu.md) | API 密钥，按量付费或 GLM Coding Plan。 |
| [小米 MiMo](./cloud/xiaomi-mimo.md) | API 密钥，按量付费或 Token Plan。 |
| [百炼套餐（Bailian Plan）](./cloud/bailian-plan.md) | 阿里云 Token Plan 或 Coding Plan 密钥。 |
| [腾讯云（Tencent Cloud）](./cloud/tencent.md) | Token Plan、Coding Plan 或按量付费密钥。 |
| [火山方舟（Volcengine Ark）](./cloud/volcengine.md) | Coding Plan、Agent Plan 或按量付费密钥。 |
| [阶跃星辰（StepFun）](./cloud/stepfun.md) | Step Plan 或按量付费密钥。 |
| [百度千帆（Baidu Qianfan）](./cloud/qianfan.md) | Token Plan 或按量付费密钥。 |
| [华为云 MaaS（Huawei Cloud MaaS）](./cloud/huaweicloud.md) | Token Plan 或按量付费密钥。 |

**中转与订阅**

| 提供商 | 你需要 |
|---|---|
| [OpenRouter](./cloud/openrouter.md) | 一个密钥即可使用数百个模型。 |
| [OpenCode Go](./cloud/opencode-go.md) | OpenCode Go 订阅密钥。 |
| [ClinePass](./cloud/clinepass.md) | ClinePass 订阅密钥。 |
| [Ollama Cloud](./cloud/ollama-cloud.md) | ollama.com 的 API 密钥。 |
| [LiteLLM Proxy](./local/litellm.md) | 你自己的 LiteLLM 代理。 |

**本地与自部署**

| 提供商 | 你需要 |
|---|---|
| [Ollama](./local/ollama.md) | 在你电脑上运行的 Ollama，无需密钥。 |
| [vLLM](./local/vllm.md) | 你自己的 vLLM 服务。 |
| [SGLang](./local/sglang.md) | 你自己的 SGLang 服务。 |

## 自定义端点

任何兼容 OpenAI 或 Anthropic 接口的服务，比如中转站或自建网关，即使不在列表里也能添加。在 **添加提供商** 的最后点击 **自定义端点**，填写：

- **名称**，显示在提供商卡片上。
- **协议**：**OpenAI 兼容** 或 **Anthropic 兼容**。
- **Base URL**。OpenAI 兼容端点通常以 `/v1` 结尾，Suzent 会自动拼接 `/chat/completions`；Anthropic 兼容端点不要带 `/v1/messages`，Suzent 会自动拼接。
- **API 密钥**，端点不需要密钥时可留空。

点击 **添加提供商**。新提供商会有自己的卡片，之后可以在上面修改密钥和 Base URL、获取模型，或用 **删除提供商** 移除它。

有了模型之后，在[模型角色](./model-roles.md)中决定每项工作由哪个模型负责。

## 小贴士

**环境变量。** 你可以在启动 Suzent 前设置 `OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 等环境变量。它们会在设置中标为 **环境变量**；在应用里保存的密钥优先生效。每个提供商的页面都列出了对应的变量。

**自定义模型。** 如果列表里没有你想要的模型，可以在提供商卡片的 **模型** 标签页里，通过 **添加模型 ID...** 输入框添加，例如 `openai/gpt-4o-2024-11-20`。

**模型信息。** Suzent 会记录每个模型的上下文窗口、价格，以及是否支持图片和工具调用。获取模型时会自动更新，通常你完全不需要操心。
