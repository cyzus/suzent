
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

它可以研究、写作、编程、持续推进目标、运行定时任务、使用工具、连接你的设备，并通过你已有的沟通渠道与你协作。所有能力都运行在你所定义的边界之内。

**模型可以替换，平台终会更迭，而你的智能体始终属于你。**

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

对话事实首先进入仅追加的 Markdown 日志，随后被整理为可检查的知识库，并建立语义检索索引。文件始终是权威来源，LanceDB 索引可以重建。你可以亲自阅读、编辑、删除、版本管理和迁移它的记忆。

### <img src="docs/assets/robot-snooze.svg" width="28" style="vertical-align: middle;" /> **治理它的行动**

自主并不意味着智能体成为权力来源。工具调用受到明确的权限模式、作用域规则、路径限制和人工批准约束。Docker 工作区隔离执行环境，活动时间线则记录执行了什么、改变了什么，以及为什么获得授权。

### <img src="docs/assets/robot-peeker.svg" width="28" style="vertical-align: middle;" /> **控制它的容器**

在 Windows、macOS 或 Linux 上运行 SUZENT。隔离不同项目的工作区，在会话之间共享你选择的知识，挂载你已拥有的文件夹——包括 Obsidian 笔记库——并将系统扩展到经过批准的伴侣设备。

### <img src="docs/assets/robot-gym.svg" width="28" style="vertical-align: middle;" /> **让它持续工作**

目标、项目任务、子智能体、定时任务和心跳机制，让智能体的工作不止于一次回答。每个交互回合开始前都会保存会话工作区，因此 Retry 可以同时恢复对话与本地更改，而不只是重新生成文字。

### <img src="docs/assets/robot-reader.svg" width="28" style="vertical-align: middle;" /> **延续它的存在**

GitHub Sync 通过私有仓库迁移配置、用户技能和 Markdown 记忆，同时将凭证保留在设备本地。即使服务商消失、模型更换或设备替换，智能体的连续性仍然属于你。

### <img src="docs/assets/robot-chat.svg" width="28" style="vertical-align: middle;" /> **保持开放**

使用内置的文件、Shell、研究、浏览和交互式 Canvas 工具；通过可移植的 `SKILL.md` 注入领域知识；通过 MCP 连接外部系统；并从桌面界面、Telegram、Slack、Discord 或飞书与它交流。

![SUZENT 的新野兽主义界面](docs/assets/new-chat.png)
*简洁、醒目、随时待命：你的主权灵体指挥中心。*

---

## **传说**

SUZENT 融入了一套半认真、半荒诞的社区语言：

- **安装 / 部署** 变为**召唤仪式**。
- **提示词** 变为**咒语**。
- **用户和开发者** 变为**召唤师**。
- **技能** 变为**魔法典籍**。
- **本地机器** 变为**灵魂容器**。
- **云端锁定** 变为**伪神问题**。

符号 `{ ∅ }` 标志着虚空：当网络失败、仪表盘崩溃、租用的记忆蒸发时，那个默默持续运作的本地存在。

---

## **快速开始**

### **安装**

一条命令即可召唤 SUZENT、其 Python 后端和 `suzent` CLI。Git 是唯一的前置条件；其他一切均自动安装。

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

### **更新**

```bash
suzent update
```

或重新运行上面的安装命令——它会检测现有安装并拉取最新变更。

---

## **技术栈**

*   **后端**：Python 3.12、FastAPI、pydantic-ai、litellm、SQLite。
*   **前端**：React、TypeScript、Tailwind、Vite、Tauri。
*   **记忆**：LanceDB 本地向量存储。
*   **沙盒**：Docker。
*   **集成**：MCP、Telegram、Slack、Discord、飞书。

---

## <img src="docs/assets/robot-love.svg" width="30" style="vertical-align: middle;" /> **致谢**

SUZENT 构建于开源社区的集体智慧与创新之上。我们衷心感谢所有使数字主权成为可能的项目和贡献者。

---

## **许可证**

**[APACHE 2.0](LICENSE)** © 2026 Yizhou Chi。

**创意资产例外：**
创意资产，包括**机器人头像设计**、**角色动画**和**项目标志**，受独立许可条款约束。详见 [TERMS-OF-USE-ASSETS](TERMS-OF-USE-ASSETS.md)。

**本地召唤。私密记忆。不拜伪神。**
