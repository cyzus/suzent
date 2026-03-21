---
sidebar_position: 1
title: 提供商
---

# 提供商

Suzent 与模型无关。在 **设置 → 提供商** 中配置任意数量的提供商，并可按会话切换。

API 密钥存储在本地数据库中——绝不以明文写入配置文件。

---

## 配置提供商

1. 打开 **设置 → 提供商**
2. 选择要添加的提供商
3. 填写凭据并点击 **保存**
4. 点击 **验证** 确认连接并加载可用模型
5. 从模型列表中启用你想使用的模型

---

## 云端提供商

### OpenAI

**模型：** GPT-4.1、GPT-4.1 Mini、o3、o4-mini

**获取密钥：** [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

| 字段 | 说明 |
|---|---|
| `OPENAI_API_KEY` | API 密钥（以 `sk-...` 开头） |
| `OPENAI_BASE_URL` | 可选。覆盖默认端点——适用于 Azure OpenAI 或兼容代理 |

---

### Anthropic

**模型：** Claude Opus 4.6、Claude Sonnet 4.6、Claude Haiku 4.5

**获取密钥：** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)

| 字段 | 说明 |
|---|---|
| `ANTHROPIC_API_KEY` | API 密钥（以 `sk-ant-...` 开头） |

---

### Google Gemini

**模型：** Gemini 2.5 Pro、Gemini 2.5 Flash、Gemini 2.0 Flash

**获取密钥（有免费额度）：** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

| 字段 | 说明 |
|---|---|
| `GEMINI_API_KEY` | API 密钥（以 `AIza...` 开头） |

`GOOGLE_API_KEY` 也可作为别名使用。

---

### xAI（Grok）

**模型：** Grok 3、Grok 3 Mini、Grok 3 Fast

**获取密钥：** [console.x.ai](https://console.x.ai)

| 字段 | 说明 |
|---|---|
| `XAI_API_KEY` | API 密钥（以 `xai-...` 开头） |

---

### DeepSeek

**模型：** DeepSeek V3（对话）、DeepSeek R1（推理）

**获取密钥：** [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys)

| 字段 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | API 密钥（以 `sk-...` 开头） |

DeepSeek R1 是推理模型——速度较慢，但更擅长多步骤问题。

---

### MiniMax

**模型：** MiniMax M2.5、MiniMax M2.1

**获取密钥：** [platform.minimaxi.com](https://platform.minimaxi.com)

| 字段 | 说明 |
|---|---|
| `MINIMAX_API_KEY` | API 密钥 |

---

### Moonshot（Kimi）

**模型：** Kimi v1 128K、Kimi v1 32K、Kimi v1 8K

**获取密钥：** [platform.moonshot.cn](https://platform.moonshot.cn)

| 字段 | 说明 |
|---|---|
| `MOONSHOT_API_KEY` | API 密钥（以 `sk-...` 开头） |

---

### 智谱 AI（GLM）

**模型：** GLM-4.7 Flash

**获取密钥：** [open.bigmodel.cn](https://open.bigmodel.cn)

| 字段 | 说明 |
|---|---|
| `ZAI_API_KEY` | API 密钥 |

---

## 聚合器与代理

### OpenRouter

通过单个 API 密钥访问 300+ 个模型——GPT、Claude、Gemini、Mistral、Llama 等。适合需要在不同提供商之间切换但不想管理多个订阅的场景。

**获取密钥：** [openrouter.ai/keys](https://openrouter.ai/keys)

| 字段 | 说明 |
|---|---|
| `OPENROUTER_API_KEY` | API 密钥（以 `sk-or-...` 开头） |

保存后点击 **获取模型** 加载完整目录。

---

### LiteLLM 代理

在任意模型集前运行自托管网关。适合团队使用、限速管理或成本追踪。

**配置文档：** [docs.litellm.ai](https://docs.litellm.ai)

| 字段 | 说明 |
|---|---|
| `LITELLM_MASTER_KEY` | 代理主密钥（以 `sk-...` 开头） |
| `LITELLM_BASE_URL` | 代理服务地址（如 `http://localhost:4000`） |

保存后点击 **获取模型** 加载代理暴露的模型。

---

## 本地运行

### Ollama

完全在本地机器上运行模型——无需 API 密钥或网络连接。

**配置：** 从 [ollama.com](https://ollama.com) 安装 Ollama，然后拉取模型：

```bash
ollama pull llama3.2
```

| 字段 | 说明 |
|---|---|
| `OLLAMA_BASE_URL` | Ollama 服务地址（默认：`http://localhost:11434`） |
| `OLLAMA_API_KEY` | 可选。仅在实例需要认证时填写 |

点击 **获取模型** 自动检测所有本地可用模型。

---

## 提示

**环境变量** —— 也可在启动 Suzent 前通过环境变量设置密钥，无需使用界面。应用优先读取数据库，再回退到环境变量。通过环境变量设置的密钥在设置界面显示为 **"来自环境变量"**，无法从界面覆盖。

**自定义模型** —— 每个提供商都可在默认列表之上添加自定义模型 ID。在 **设置 → 提供商 → [提供商] → 自定义模型** 中，按 LiteLLM 格式填写模型 ID：`provider/model-name`（如 `openai/gpt-4o-2024-11-20`）。
