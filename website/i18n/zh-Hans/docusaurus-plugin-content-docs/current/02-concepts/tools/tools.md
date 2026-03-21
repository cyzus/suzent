---
title: 工具
---

# 工具

工具扩展了智能体的能力，使其能够与文件系统、网络、记忆、社交平台等进行交互。每个工具都是一个**函数**，通过工具注册表注册到 pydantic-ai `Agent` 上。

## 可用工具

### 网络与搜索

| 工具 | 说明 |
|------|-------------|
| WebSearchTool | 通过 SearXNG 或 DuckDuckGo 进行网络搜索 |
| WebpageTool | 抓取网页并提取为 Markdown 内容 |
| BrowsingTool | 控制无头浏览器（Playwright） |

### 文件系统

| 工具 | 需审批 | 说明 |
|------|------|-------------|
| ReadFileTool | — | 读取文件（文本、PDF、DOCX、图片 OCR） |
| WriteFileTool | **是** | 创建或覆盖文件 |
| EditFileTool | **是** | 文件中的精确文本替换 |
| GlobTool | — | 按 Glob 模式查找文件 |
| GrepTool | — | 用正则表达式搜索文件内容 |

### 执行

| 工具 | 需审批 | 说明 |
|------|------|-------------|
| BashTool | **是** | 执行代码/命令（Python、Node.js、Shell） |

### 规划与记忆

| 工具 | 说明 |
|------|-------------|
| PlanningTool | 创建和管理结构化任务计划 |
| MemorySearchTool | 对长期记忆进行语义搜索 |
| MemoryBlockUpdateTool | 更新核心记忆块（角色、用户、事实、上下文） |

### 社交与输出

| 工具 | 需审批 | 说明 |
|------|------|-------------|
| SocialMessageTool | **是** | 向 Telegram、Discord、Slack、Feishu 发送消息 |
| SpeakTool | — | 文字转语音输出 |
| SkillTool | — | 执行用户定义的技能 |

**需审批** = 执行前需要人工确认。详见[人机协同](human-in-the-loop)。

---

## 人机协同（HITL）

写文件、执行 Bash 命令、发送消息等高风险操作在执行前需要用户确认。详见[人机协同文档](human-in-the-loop)。

---

## MCP 工具集成

Suzent 支持通过 MCP（Model Context Protocol）协议连接外部工具服务器，可接入 Google Drive、GitHub、Slack 等第三方服务。详见开发指南中的 MCP 配置部分。
