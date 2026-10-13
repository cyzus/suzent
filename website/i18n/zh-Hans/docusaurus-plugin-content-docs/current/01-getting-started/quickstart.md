---
sidebar_position: 2
title: 快速开始
description: 安装 Suzent、连接模型，几分钟内发出第一条消息。
---

import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

# 快速开始

几分钟内启动 Suzent。

---

## 1. 安装

### 使用安装程序

从[首页](/#download)下载适合你电脑的安装程序。M 系列 Mac 选择 Apple Silicon，Intel Mac 选择 Intel。Windows 和 Linux 下载适用于 x86_64。

在 Windows 上打开下载的 `.exe`。在 macOS 或 Linux 上，在下载文件夹中打开终端，将 `<filename>` 替换为下载的安装程序的完整文件名后运行：

```bash
chmod +x ./<filename>
./<filename>
```

按照安装程序的引导选择工作区并安装 Suzent。安装需要联网。当前发行版在 macOS 和 Linux 上需要 Git；如果安装程序提示缺少 Git，请先安装 Git。

### 使用终端

**前提条件：** [Node.js 20+](https://nodejs.org/) 和 [Git](https://git-scm.com/downloads)。

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
```

</TabItem>
</Tabs>

安装脚本会自动安装 Suzent 及所有缺失的依赖项（Python/uv、Rust、构建工具等）。

### 中国大陆镜像模式

如果从中国大陆下载依赖较慢，可以在运行安装脚本前开启镜像模式：

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
$env:SUZENT_CHINA_MIRROR="1"; powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | SUZENT_CHINA_MIRROR=1 bash
```

</TabItem>
</Tabs>

镜像模式会为 PyPI、npm、Playwright、Node（通过 nvm）和 Rustup 配置国内镜像。如果访问 GitHub 本身也很慢，可在运行前把 `SUZENT_REPO_URL` 或 `SUZENT_RELEASE_BASE_URL` 设为你信任的镜像地址。

---

## 2. 启动

```bash
suzent start
```

此命令会启动后端并打开桌面界面。

---

## 3. 添加模型提供商

界面打开后，进入 **设置 → 提供商** 配置 API 密钥。以下是最常用的三个提供商：

<Tabs groupId="provider">
<TabItem value="openai" label="OpenAI" default>

**获取密钥：** [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → 创建新密钥（以 `sk-...` 开头）

在设置中打开 OpenAI 卡片 → **API 密钥** 标签页 → **修改** → 粘贴密钥。然后切到 **模型** 标签页 → **获取**，勾选需要的模型，点击 **保存更改**。

</TabItem>
<TabItem value="anthropic" label="Anthropic">

**获取密钥：** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → 创建密钥（以 `sk-ant-...` 开头）

在设置中打开 Anthropic 卡片 → **API 密钥** 标签页 → **修改** → 粘贴密钥。然后切到 **模型** 标签页 → **获取**，勾选需要的模型，点击 **保存更改**。

</TabItem>
<TabItem value="gemini" label="Google Gemini">

**获取密钥（有免费额度）：** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → 创建 API 密钥（以 `AIza...` 开头）

在设置中打开 Google Gemini 卡片 → **API 密钥** 标签页 → **修改** → 粘贴密钥。然后切到 **模型** 标签页 → **获取**，勾选需要的模型，点击 **保存更改**。

</TabItem>
</Tabs>

使用 DeepSeek、Grok、OpenRouter、Ollama、ChatGPT 订阅或其他提供商？请查看[模型与提供商](../04-models/README.md)。

---

## 4. 开始对话

在聊天窗口的模型选择器中选择一个模型，发送第一条消息即可。

**就这样。** 记忆系统、工具和自动化功能开箱即用。可以试着让它记住一件关于你的事，或者让它调研一个话题并把摘要写进文件。

---

<a id="troubleshooting"></a>

## 故障排查

**"找不到命令：suzent"** ——安装后重启终端以刷新 `PATH`。若仍无效，查看安装脚本输出，按提示手动添加脚本目录到 PATH。

**"系统健康检查失败"**

```bash
suzent doctor
```

**启动时端口冲突** —— 如果端口已被占用，`suzent start` 会停止并告诉你是哪个进程占用了它。通常是另一个正在运行的 Suzent：运行 `suzent stop`，或用 `suzent start --port <端口>` 换一个端口启动。

**更新** —— 运行 `suzent update`，或查看[更新 Suzent](./updating.md)。

更多问题见[常见问题与故障排查](../07-reference/faq.md)。

---

## 后续步骤

- [和智能体一起工作](../02-using/conversations.md)：交代任务、中途纠正、撤销出错的操作
- [按你的需要设置](../02-using/make-it-yours.md)：接下来值得设置的东西
- [桌面、手机和浏览器](./platforms.md)：从手机或另一台电脑使用你的智能体
- [模型与提供商](../04-models/README.md)：添加更多模型，并决定每项工作用哪个模型
- [记忆](../03-features/memory/README.md)：智能体记住了什么，以及如何修改
- [工具](../03-features/tools/README.md)：智能体能做的所有事
- [聊天应用](../05-chat-apps/README.md)：通过 Telegram、Slack 等与它对话
- [自动化](../03-features/automation.md)：安排定时任务和定期检查
