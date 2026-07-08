
<div align="center">

![Suzent Banner](docs/assets/banner_v2.png)

# **SUZENT：召唤主权灵体**

![状态](https://img.shields.io/badge/仪式-就绪-black?style=flat-square) ![系统](https://img.shields.io/badge/灵体-本地优先-black?style=flat-square)

[![版本](https://img.shields.io/github/v/release/cyzus/suzent?style=flat-square&label=版本)](https://github.com/cyzus/suzent/releases) [![许可证](https://img.shields.io/github/license/cyzus/suzent?style=flat-square)](LICENSE) [![Python](https://img.shields.io/badge/python-3.12%2B-yellow?style=flat-square)](https://python.org) [![Discord](https://img.shields.io/badge/Discord-加入聊天-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/MkBDDbwPBK)


**[召唤仪式](docs/01-getting-started/quickstart.md)** • **[魔法典籍](docs/README.md)** • **[贡献指南](./CONTRIBUTING.md)**



</div>

---

## <img src="docs/assets/robot-idle.svg" width="30" style="vertical-align: middle;" /> **数字神秘主义**

> 你的数据。你的机器。你的规则。

SUZENT [soo-zuh-nt] 由 SUZERAIN（宗主）和 AGENT（执行者）合并而来。它不是云端宠物，不是 SaaS 仪表盘，也不是藏在别人 API 配额背后的租用人格。它是一个本地优先的智能体系统，只听命于一个权威：你。

把它想象成一个**主权灵体**：一个驻扎在你自己机器上的赛博精灵，通过终端咒语召唤，由本地文件、记忆、工具和技能所约束。玩笑是仪式，仪式是接口。

---

## **为何选择 SUZENT？**

SUZENT 是一个开源的深度研究与协作智能体，拥有本地优先的灵魂。它将现代 AI 智能体、研究助手、编程协作者、MCP 工具生态系统和个人知识工作流的理念融为一体，构建成一个你可以真正运行、检查、修改和拥有的系统。

它既是一个实用工具，也是面向开发者的参考实现：工作区隔离、持久记忆、工具执行、定时自动化、社交渠道集成，以及桌面 UI，全部集成在一个连贯的技术栈中。

这套神话体系是刻意为之的：云服务虽然有用，但你的智能体不应该需要朝圣至他人的服务器才能记住你的工作。


## **功能特性**

### <img src="docs/assets/robot-agnostic.svg" width="28" style="vertical-align: middle;" /> **模型无关**

带上你自己的神谕。**SUZENT** 与模型无关，可以使用 GPT、Claude、Gemini、DeepSeek、本地模型，或通过支持的模型栈暴露的任何提供商。

### <img src="docs/assets/robot-gym.svg" width="28" style="vertical-align: middle;" /> **智能体工作流**

**SUZENT** 提供与深度研究和协作产品相媲美的丰富智能体工作流，但拥有开源代码、本地工作区、可检查的工具，以及你可以自由重塑的架构。

### <img src="docs/assets/robot-reader.svg" width="28" style="vertical-align: middle;" /> **工具与技能**

**SUZENT** 内置了用于实际工作的实用工具：`bash`、网络搜索、网络抓取和文件操作。这些构成了研究、编程、写作和分析的基本仪式圈。

你可以创建自定义工具，并通过标准 MCP 协议进一步连接 Google Drive、GitHub 或 Slack。

完全支持智能体技能。将你喜欢的技能典籍放入 `./skills`，智能体即可加载新工作流，无需重写核心代码。

### <img src="docs/assets/robot-peeker.svg" width="28" style="vertical-align: middle;" /> **工作区**

与大多数智能体不同，**SUZENT** 使用双工作区：一个跨会话共享的工作区用于持久知识，以及每个会话独立的工作区用于单次对话。这在保持隔离性的同时提供了连续性。你还可以直接将本地文件夹（包括 Obsidian 笔记库）挂载到系统中。

### <img src="docs/assets/robot-thinking.svg" width="28" style="vertical-align: middle;" /> **记忆**

**SUZENT** 实现了跨会话持久化的全局记忆系统。你的智能体可以积累上下文、回忆先前的工作，并在你的机器上构建私有知识基底。

### <img src="docs/assets/robot-clock.svg" width="28" style="vertical-align: middle;" /> **自动化**

**SUZENT** 支持两套自动化系统，用于主动的、定时的智能体执行：
- **定时任务（Cron Jobs）** — 在隔离的会话中按任意 cron 表达式调度提示词运行。通过设置界面、CLI（`suzent cron`）和 REST API 进行完整的增删改查操作。
- **心跳（Heartbeat）** — 定期的环境监控，读取你在聊天中配置的每会话清单，仅在需要关注时通知你。

两套系统均启用完整的记忆功能，因此智能体在定时任务之间可以保留上下文。

### <img src="docs/assets/robot-chat.svg" width="28" style="vertical-align: middle;" /> **社交集成**

**SUZENT** 连接你的消息平台，让你可以在已有的沟通渠道中与智能体互动：
- **Telegram** — 通过 Telegram 机器人与你的智能体聊天。
- **Slack** — 作为 Slack 应用集成到你的工作区。
- **Discord** — 在你的服务器中作为 Discord 机器人运行。
- **飞书（Lark）** — 通过飞书开放平台连接。

### <img src="docs/assets/robot-snooze.svg" width="28" style="vertical-align: middle;" /> **私密且本地**

**SUZENT** 在你的设备上运行，采用注重隐私的网络搜索、用于本地向量存储的 LanceDB，以及用于更安全代码执行的 Docker 隔离。除非你明确连接外部服务，否则你的数据始终保留在你的容器中。

### <img src="docs/assets/robot-party.svg" width="28" style="vertical-align: middle;" /> **界面就绪**

**SUZENT** 提供了一个新野兽主义（NeoBrutalist）风格的 Web 界面，将基于终端的智能体交互转变为一个锐利、高对比度的命令界面：部分是工作台，部分是祭坛，部分是本地机房。

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
