<div align="right">

*[English](README.md)*

</div>

<div align="center">

![Suzent Banner](docs/assets/banner_v2.png)

# **SUZENT：主权 AI 智能体**

### **你的智能体不应是一个租来的账号。**

![状态](https://img.shields.io/badge/仪式-就绪-black?style=flat-square) ![系统](https://img.shields.io/badge/灵体-本地优先-black?style=flat-square)

[![版本](https://img.shields.io/github/v/release/cyzus/suzent?style=flat-square&label=版本)](https://github.com/cyzus/suzent/releases) [![许可证](https://img.shields.io/github/license/cyzus/suzent?style=flat-square)](LICENSE) [![Python](https://img.shields.io/badge/python-3.12%2B-yellow?style=flat-square)](https://python.org) [![Discord](https://img.shields.io/badge/Discord-加入聊天-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/MkBDDbwPBK)


**[官方网站](https://suzent.com/zh-Hans/)** • **[召唤仪式](docs/01-getting-started/quickstart.md)** • **[魔法典籍](docs/README.md)** • **[贡献指南](./CONTRIBUTING.md)**



</div>

---

## <img src="docs/assets/robot-idle.svg" width="30" style="vertical-align: middle;" /> **召唤主权灵体**

> 你的智能体不应是一个租来的账号，而应是一个真正属于你的系统。

**SUZENT** [soo-zuh-nt] 是一个开源、本地优先的 AI 智能体。它的身份、记忆、技能、工作区和运行环境始终处于你的控制之下。你可以使用 GPT、Claude、Gemini、DeepSeek、本地模型，以及未来出现的任何兼容模型，而无需重置那个了解你和你的工作的智能体。

它的记忆是存放在你磁盘上的仅追加 Markdown 文件，而不是别人数据库里的几行记录。它的工具调用必须经过你定义的权限模式。它的执行被隔离在你自己拥有的 Docker 工作区中。它可以研究、写作、编程、持续推进目标、运行定时任务、连接你的设备，并在 Telegram、Slack、Discord、飞书或微信中与你会合——始终运行在你所设定的边界之内。

**模型可以替换，平台终会更迭，而你的智能体始终属于你。**

---

## **快速开始**

### **安装**

SUZENT 可运行在 Windows、macOS 和 Linux 上。一条命令即可召唤它、其 Python 后端和 `suzent` CLI。Git 是唯一的前置条件；其他一切均自动安装。

**macOS / Linux**
```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | bash
```

**Windows**（PowerShell）
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

**中国大陆镜像模式**
```bash
curl -fsSL https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.sh | SUZENT_CHINA_MIRROR=1 bash
```

```powershell
$env:SUZENT_CHINA_MIRROR="1"; powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/cyzus/suzent/main/scripts/setup.ps1 | iex"
```

该模式会为 PyPI、npm、Playwright、nvm 下载 Node，以及 Rustup 启用国内镜像。如果 GitHub 本身访问较慢，可在运行前把 `SUZENT_REPO_URL` 或 `SUZENT_RELEASE_BASE_URL` 设置为你信任的镜像地址。

然后在 `~/suzent/.env` 中绑定你的密钥并运行：

```bash
suzent start
```

### **`suzent` 命令行**

```bash
suzent start           # 启动后端与桌面应用
suzent serve           # 仅启动后端（无界面 / 独立模式）
suzent ui              # 连接已运行的后端，仅启动桌面应用
suzent stop            # 停止正在运行的后端服务
suzent doctor          # 检查依赖环境，诊断安装问题
suzent update          # 更新到最新稳定版
suzent check-update    # 查看是否有新版本可用
suzent repair          # 修复中断或损坏的更新
```

运行 `suzent --help` 或 `suzent <命令> --help` 查看完整参数。

### **更新**

```bash
suzent update
```

该命令会将最新稳定版作为一个匹配的整体安装：后端源码、锁定的依赖和桌面应用。独立更新器会在当前虚拟环境之外执行切换，校验下载的文件，并在失败时自动回滚。如果更新被中断需要恢复，请运行：

```bash
suzent repair
```

从源码检出进行开发的用户，直接运行 `suzent update` 即可同时更新 `main` 分支及其前端依赖——检出目录会被自动识别。等价的显式写法是：

```bash
suzent update --dev
```

或重新运行上面的安装命令——它会检测现有安装并更新到最新稳定版。

---

## **什么才是主权智能体？**

| 问题 | SUZENT 的回答 |
|---|---|
| 谁拥有它的记忆？ | **你。** Markdown 文件是持久、权威的事实来源。 |
| 谁选择它的智能？ | **你。** 模型和服务提供商随时可以替换。 |
| 谁规定它可以做什么？ | **你。** 权限、规则和沙箱边界清晰可见。 |
| 它生活在哪里？ | **在你控制的基础设施上。** |
| 它可以迁移吗？ | 记忆、技能和配置可以迁移，凭证始终留在本地。 |
| 你能检查它吗？ | 工具调用、授权决策、文件和记忆都保持可见。 |

主权不只是本地运行，而是拥有智能体的**心智、权力、容器与连续性**。

## **主权系统**

### <img src="docs/assets/robot-agnostic.svg" width="28" style="vertical-align: middle;" /> **选择它的智能**

模型是引擎，而不是身份。你可以在 GPT、Claude、Gemini、DeepSeek、本地模型和兼容提供商之间切换，同时保留真正让这个智能体属于你的记忆、技能和工作区。

### <img src="docs/assets/robot-thinking.svg" width="28" style="vertical-align: middle;" /> **拥有它的记忆**

对话事实首先进入仅追加的 Markdown 日志，随后被整理为可检查的知识库，并建立语义检索索引——文件始终是权威来源，LanceDB 索引随时可以由它们重建。你可以亲自阅读、编辑、删除、版本管理和迁移这份记忆。

### <img src="docs/assets/robot-snooze.svg" width="28" style="vertical-align: middle;" /> **治理它的行动**

自主并不意味着智能体成为权力来源。工具调用受到明确的权限模式、作用域规则、路径限制和人工批准约束。Docker 工作区隔离执行环境，活动时间线则记录执行了什么、改变了什么，以及为什么获得授权。

### <img src="docs/assets/robot-gym.svg" width="28" style="vertical-align: middle;" /> **随处运行，持续工作**

目标、项目任务、子智能体、定时任务和心跳机制，让智能体的工作不止于一次回答——它们运行在相互隔离的项目工作区、你已拥有的文件夹（包括 Obsidian 笔记库），以及经过批准的伴侣设备之上。每个交互回合开始前都会保存会话工作区，因此 Retry 可以同时恢复对话与本地更改，而不只是重新生成文字。

你还可以通过可移植的 `SKILL.md` 技能包和任意 MCP 服务进一步扩展它。

### <img src="docs/assets/robot-reader.svg" width="28" style="vertical-align: middle;" /> **延续它的存在**

GitHub Sync 通过私有仓库迁移配置、用户技能和 Markdown 记忆，同时将凭证保留在设备本地。即使服务商消失、模型更换或设备替换，智能体的连续性仍然属于你。

---

## **在哪里与它对话**

同一个智能体，同一份记忆，可从多个入口触达。消息渠道默认关闭并受访问控制：用户 ID 必须出现在 `allowed_users` 中，智能体才会回应。

| 入口 | 传输方式 | 支持内容 | 配置 |
|---|---|---|---|
| **桌面应用** | 本地后端 | 完整界面、Canvas、记忆与技能面板 | `suzent start` |
| **Telegram** | Bot API | 文本、图片、文件 | [指南](docs/02-concepts/social-messaging/telegram.md) |
| **Slack** | Socket Mode（Events API） | 文本、文件 | [指南](docs/02-concepts/social-messaging/slack.md) |
| **Discord** | Gateway | 文本、文件 | [指南](docs/02-concepts/social-messaging/discord.md) |
| **飞书（Lark）** | WebSocket | 文本、文件 | [指南](docs/02-concepts/social-messaging/feishu.md) |
| **微信** | iLink Bot API | 文本 | [指南](docs/02-concepts/social-messaging/wechat.md) |

每个对话都会成为一个持久会话，因此历史记录、工作记忆和提取的事实都能在重启后保留。上传的文件会落在沙盒的 `/persistence/uploads/` 目录中。

---

## **魔法典籍**

| 章节 | 内容 |
|---|---|
| [什么是 Suzent？](docs/01-getting-started/intro.md) | 核心概念与架构总览 |
| [快速上手](docs/01-getting-started/quickstart.md) | 5 分钟内从零搭建 SUZENT |
| [模型提供商](docs/02-concepts/providers/README.md) | OpenAI、Anthropic、Gemini、Ollama 等 |
| [记忆](docs/02-concepts/memory/README.md) | 持久记忆的原理与配置方式 |
| [LLM Wiki](docs/02-concepts/memory/llm-wiki.md) | 由智能体维护的结构化知识库 |
| [工具](docs/02-concepts/tools/tools.md) | 全部内置工具的完整参考 |
| [Canvas（A2UI）](docs/02-concepts/tools/canvas.md) | 在侧边栏渲染的交互式界面 |
| [工具审批](docs/02-concepts/tools/human-in-the-loop.md) | 危险工具如何要求人工确认 |
| [技能](docs/02-concepts/skills/skills.md) | 用可移植的知识模块扩展智能体 |
| [文件系统与沙盒](docs/02-concepts/filesystem.md) | 文件访问、沙盒执行与存储路径 |
| [自动化](docs/02-concepts/automation/automation.md) | 定时任务与心跳监控 |
| [GitHub 同步](docs/02-concepts/github-sync/README.md) | 通过私有仓库迁移可移植的大脑数据 |
| [社交消息](docs/02-concepts/social-messaging/README.md) | Telegram、Slack、Discord、飞书、微信 |
| [节点](docs/02-concepts/nodes/nodes.md) | 连接并控制伴侣设备 |
| [Retry](docs/02-concepts/runtime/retry.md) | 回滚上一轮并重新运行 |
| [开发指南](docs/03-developing/development-guide.md) | 环境搭建、工作流、构建与架构 |

完整索引见 [docs/README.md](docs/README.md)。

---

## **传说**

SUZENT 的文档和社区使用一套神秘学语汇。玩笑背后有其道理：对于一个真正属于你的智能体来说，召唤与附身的词汇远比席位、套餐和账号的词汇更贴切。如果你在这些页面里遇到陌生的词，多半能在这里找到。

| 术语 | 含义 |
|---|---|
| **召唤仪式** | 安装与部署 SUZENT |
| **咒语** | 提示词 |
| **召唤师** | 你——使用者、运维者、开发者 |
| **魔法典籍** | 智能体可以学习的技能，以及讲解它的文档 |
| **灵魂容器** | 运行智能体的那台机器 |
| **伪神** | 云端锁定：停止付费后就把你忘光的租用智能体 |
| **`{ ∅ }`** | 虚空——当网络失败、仪表盘崩溃、租用的记忆蒸发时，那个默默持续运作的本地存在 |

---

## **技术栈**

*   **后端**：Python 3.12、FastAPI、pydantic-ai、litellm、SQLite。
*   **前端**：React、TypeScript、Tailwind、Vite、Tauri。
*   **记忆**：LanceDB 本地向量存储。
*   **沙盒**：Docker。
*   **扩展性**：MCP、可移植的 `SKILL.md` 技能包。

---

## **贡献**

欢迎各位召唤师。完整流程见 [CONTRIBUTING.md](./CONTRIBUTING.md)，环境搭建、生产构建与架构说明见[开发指南](docs/03-developing/development-guide.md)。

---

## **安全**

发现安全漏洞？请通过私密渠道报告——详见 [SECURITY.md](SECURITY.md)。请勿提交公开 issue。

---

## **许可证**

**[APACHE 2.0](LICENSE)** © 2026 Yizhou Chi。

**创意资产例外：**
创意资产，包括**机器人头像设计**、**角色动画**和**项目标志**，受独立许可条款约束。详见 [TERMS-OF-USE-ASSETS](TERMS-OF-USE-ASSETS.md)。

**本地召唤。私密记忆。不拜伪神。**
