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

### 从 Microsoft Store 安装（Windows，推荐）

<a href="https://apps.microsoft.com/detail/9MZQ1HHXHVZT?mode=full"><img src="https://get.microsoft.com/images/zh-cn%20dark.svg" alt="从 Microsoft 获取" width="200" /></a>

在 Store 中点击 **获取**，然后从开始菜单打开 Suzent。Python、Git 等依赖都已内置，无需另外安装。接着直接进行[第 3 步](#3-添加模型提供商)。

Store 版与安装程序版的区别：

- **通过 Microsoft Store 更新。** Store 版中 `suzent update`、`suzent upgrade` 和 `suzent repair` 已停用。
- **数据仍保存在 `~/.suzent`**（对话、记忆、设置、API 密钥），与安装程序版相同；卸载应用不会删除这些数据。
- **开机启动**（设置 → 后台服务）使用 Windows 的启动应用设置，也可以在 Windows 设置 → 应用 → 启动 中关闭。
- **可以与安装程序版同时安装。** 两者共用 `~/.suzent`，但不要同时运行：Store 版不会连接安装程序版启动的后端，而会在同一份数据上再启动一个后端。打开其中一个之前，请先退出另一个（包括它的后台服务），并且只在其中一个里开启开机启动。

### 使用安装程序

从[首页](/#download)下载适合你电脑的安装程序。macOS 安装包为 Universal 通用版，同时原生支持 Apple Silicon（M 系列）与 Intel Mac。Windows 和 Linux 下载适用于 x86_64。

- **macOS：** 打开下载的 `.dmg`，然后双击 **Suzent Installer**。也可以先把它拖到“应用程序”文件夹，再从那里打开。
- **Windows：** 打开下载的 `.exe`。
- **Linux：** 在下载文件夹中打开终端，将 `<filename>` 替换为下载的安装程序的完整文件名后运行：

  ```bash
  chmod +x ./<filename>
  ./<filename>
  ```

按照安装程序的引导选择工作区并安装 Suzent。安装需要联网。当前发行版在 macOS 和 Linux 上需要 Git；如果安装程序提示缺少 Git，请先安装 Git。

### 使用终端

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

这条命令会下载和桌面安装程序相同的应用，全程无需操作：

- **Windows：** 装到 `%LOCALAPPDATA%\Programs\Suzent`，并创建开始菜单和桌面快捷方式。想换目录，先设置 `$env:SUZENT_APP_DIR`。
- **Mac：** 装到“应用程序”（主“应用程序”文件夹不可写时，装到个人目录下的“应用程序”）。
- **有桌面的 Linux：** Debian 和 Ubuntu 上安装 `.deb` 包（会要求输入密码），其他发行版在 `~/.local/share/suzent/app` 放一份便携版，并加入应用菜单。
- **没有显示器的 Linux 服务器：** 同样是便携版。运行 `suzent serve` 启动后端，或运行 `suzent web` 在浏览器里使用。再运行一次这条命令即可更新。

之后应用会自己保持更新。无论用哪种方式安装，数据都在 `~/.suzent`。

应用暂不支持的电脑（Intel Mac、ARM Linux），或发行版里没有安装包时，命令会改为从源码安装。这需要 [Git](https://git-scm.com/downloads)，Python、uv 等依赖会自动安装。

**开发者：** 加上 `--source` 可以得到能直接开发的 git 源码目录（`curl … | bash -s -- --source`，PowerShell 则先设置 `$env:SUZENT_INSTALL="source"`）。已有的源码安装会继续按源码方式更新。

### 在中国大陆安装

安装脚本会根据当前网络自动选择下载源：连不上 Google、但能连上国内镜像时，Suzent 代码（Gitee 镜像）、Python、依赖包、Playwright 浏览器和 uv 都会从国内镜像下载，不需要手动开启。国内镜像暂时还没有应用安装包，所以在这类网络下会通过镜像从源码安装；加上 `--package`（或设置 `SUZENT_INSTALL=package`）可以改为从 GitHub 下载应用。

如果 `raw.githubusercontent.com` 打不开，可以从 jsDelivr 获取同一个脚本：

<Tabs groupId="os">
<TabItem value="windows" label="Windows" default>

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://cdn.jsdelivr.net/gh/cyzus/suzent@main/scripts/setup.ps1 | iex"
```

</TabItem>
<TabItem value="mac-linux" label="Mac / Linux">

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/cyzus/suzent@main/scripts/setup.sh | bash
```

</TabItem>
</Tabs>

想强制开启或关闭镜像，在运行前设置 `SUZENT_CHINA_MIRROR=1` 或 `SUZENT_CHINA_MIRROR=0`。如果访问 GitHub 本身也很慢，可把 `SUZENT_REPO_URL` 或 `SUZENT_RELEASE_BASE_URL` 设为你信任的镜像地址。

---

## 2. 启动

```bash
suzent start
```

此命令会启动后端并打开桌面界面。

---

## 3. 添加模型提供商

新安装、还没有配置任何模型提供商时，聊天界面会打开设置向导。之后也可以在 **设置 → 关于** 里打开 **设置向导**：

1. **选一个服务。** Suzent 会按你所在的地方推荐四个服务（在中国大陆网络下，国内服务排在前面）。**更多服务** 列出其余服务；**手动配置** 打开完整的提供商列表，适合自定义地址或一次设置多个服务。
2. **连接。** 按链接去创建 API 密钥，粘贴后点 **连接**。Suzent 会保存密钥、列出这个服务的模型，并发一条很短的测试消息，所以密钥不对、余额不足或网络不通都会在这里用大白话说明，而不是等到第一次对话才出错。ChatGPT 用你的订阅登录，不需要密钥；Ollama 这类在本机运行的服务会要你填地址。
3. **完成。** 选好默认的聊天模型，点 **开始聊天**。起标题、整理记忆这类后台小事，会自动交给这个服务里合适的模型，已有的分配不会被改动。之后可以在 **设置 → 模型角色** 里调整。

想自己添加提供商，或之后再加一个，进入 **设置 → 提供商**。以下是最常用的三个提供商：

<Tabs groupId="provider">
<TabItem value="openai" label="OpenAI" default>

**获取密钥：** [platform.openai.com/api-keys](https://platform.openai.com/api-keys) → 创建新密钥（以 `sk-...` 开头）

在设置的 **添加提供商** 里找到 **OpenAI** 并打开它的卡片。在 **API 密钥** 标签页粘贴密钥，点击 **保存**。然后点击 **测试连接**，它的模型就会出现在聊天的模型选择器里。改动会自动保存。

</TabItem>
<TabItem value="anthropic" label="Anthropic">

**获取密钥：** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) → 创建密钥（以 `sk-ant-...` 开头）

在设置的 **添加提供商** 里找到 **Anthropic** 并打开它的卡片。在 **API 密钥** 标签页粘贴密钥，点击 **保存**。然后点击 **测试连接**，它的模型就会出现在聊天的模型选择器里。改动会自动保存。

</TabItem>
<TabItem value="gemini" label="Google Gemini">

**获取密钥（有免费额度）：** [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) → 创建 API 密钥（以 `AIza...` 开头）

在设置的 **添加提供商** 里找到 **Google Gemini** 并打开它的卡片。在 **API 密钥** 标签页粘贴密钥，点击 **保存**。然后点击 **测试连接**，它的模型就会出现在聊天的模型选择器里。改动会自动保存。

</TabItem>
</Tabs>

使用 DeepSeek、通义千问、Kimi、GLM、各家编程套餐、OpenRouter、Ollama、ChatGPT 订阅或其他提供商？请查看[模型与提供商](../04-models/README.md)。

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

- [和智能体一起工作](../02-using/conversations.md)：交代任务、中途纠正、某一轮出错时怎么办
- [按你的需要设置](../02-using/make-it-yours.md)：接下来值得设置的东西
- [桌面、手机和浏览器](./platforms.md)：从手机或另一台电脑使用你的智能体
- [模型与提供商](../04-models/README.md)：添加更多模型，并决定每项工作用哪个模型
- [记忆](../03-features/memory/README.md)：智能体记住了什么，以及如何修改
- [工具](../03-features/tools/README.md)：智能体能做的所有事
- [聊天应用](../05-chat-apps/README.md)：通过 Telegram、Slack 等与它对话
- [自动化](../03-features/automation.md)：安排定时任务和定期检查
