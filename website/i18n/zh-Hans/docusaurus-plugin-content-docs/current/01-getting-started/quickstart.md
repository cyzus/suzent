---
sidebar_position: 2
title: 快速开始
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# 快速开始

5 分钟内启动 Suzent。

---

## 1. 安装

**前提条件：** [Node.js 20+](https://nodejs.org/) 和 [Git](https://git-scm.com/downloads)。

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

安装脚本会自动安装 Suzent 及所有缺失的依赖项（Python/uv、Rust、构建工具等）。

---

## 2. 启动

```bash
suzent start
```

此命令会启动后端并在浏览器中打开界面。默认地址为 `http://localhost:25315`。

---

## 3. 添加模型提供商

界面打开后，进入 **设置 → 提供商** 配置 API 密钥。以下是最常用的三个提供商：

<Tabs groupId="provider">
<TabItem value="openai" label="OpenAI" default>

**获取密钥：** [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → 创建新密钥（以 `sk-...` 开头）

在设置中，将密钥粘贴到 **OpenAI → API Key**，启用所需模型，然后点击 **保存 → 验证**。

</TabItem>
<TabItem value="anthropic" label="Anthropic">

**获取密钥：** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → 创建密钥（以 `sk-ant-...` 开头）

在设置中，将密钥粘贴到 **Anthropic → API Key**，启用所需模型，然后点击 **保存 → 验证**。

</TabItem>
<TabItem value="gemini" label="Google Gemini">

**获取密钥（有免费额度）：** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → 创建 API 密钥（以 `AIza...` 开头）

在设置中，将密钥粘贴到 **Google Gemini → API Key**，启用所需模型，然后点击 **保存 → 验证**。

</TabItem>
</Tabs>

使用 DeepSeek、Grok、OpenRouter、Ollama 或其他提供商？请查看完整的[提供商参考](../concepts/providers)。

---

## 4. 开始对话

在聊天窗口的模型选择器中选择一个模型，发送第一条消息即可。

**就这样。** 记忆系统、工具和自动化功能开箱即用。

---

## 故障排查

**"找不到命令：suzent"** ——安装后重启终端以刷新 `PATH`。若仍无效，查看安装脚本输出，按提示手动添加脚本目录到 PATH。

**"系统健康检查失败"**

```bash
suzent doctor
```

**启动时端口冲突** —— `suzent start` 会检测冲突并询问是否终止占用进程，输入 `y` 继续。

**更新**

```bash
suzent upgrade
```

---

## 后续步骤

- [Suzent 是什么？](./intro) —— 了解整体架构
- [提供商](../concepts/providers) —— 完整的模型与提供商列表
- [工具](../concepts/tools) —— 查看智能体的所有能力
- [记忆系统](../concepts/memory) —— 了解持久记忆的工作原理
- [自动化](../concepts/automation) —— 定时任务与心跳监控
