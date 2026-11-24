---
sidebar_position: 4
title: 让其他 agent 共享记忆
description: 让电脑上的 Claude Code、Codex、Cursor 等 AI 应用搜索你的 Suzent 记忆，经你允许后还能写入。
---

# 让其他 agent 共享记忆

Suzent 记得你是谁、你喜欢什么、上次什么办法管用。你用的其他 AI 应用也可以共享这份记忆，
这样在 Claude Code、Codex 或 Cursor 里就不用再把自己重新介绍一遍。

你的记忆始终由你掌控：它不会离开你的电脑。其他应用只和同一台电脑上运行的 Suzent 通信，
记忆文件仍然只由 Suzent 保管。

## 连接应用

先确保 Suzent 正在运行，然后把它作为 MCP 服务器加到应用里。

**Claude Code**

```bash
claude mcp add suzent -- suzent mcp serve
```

**Codex**

```bash
codex mcp add suzent -- suzent mcp serve
```

**其他应用**（Cursor、Claude Desktop、Windsurf 等）：添加一个在本机运行的 MCP 服务器，
命令填 `suzent`，参数填 `mcp serve`。写在 JSON 配置文件里是这样：

```json
{
  "mcpServers": {
    "suzent": { "command": "suzent", "args": ["mcp", "serve"] }
  }
}
```

**设置 → 记忆系统 → 其他 agent** 里也有这条命令，可以一键复制。

## 应用能做什么

| 工具 | 作用 |
|---|---|
| `memory_search` | 按意思搜索你的记忆，比如"我喜欢用哪个包管理器"。 |
| `memory_profile` | 读取 Suzent 对你的了解：你是谁、你的偏好和关键事实。 |
| `memory_remember` | 保存一条新记忆。默认关闭，需要你允许。 |

本机应用随时可以读取。写入默认关闭，要在 **设置 → 记忆系统 → 其他 agent** 里打开
**允许它们保存记忆**。

应用保存记忆时：

- 记忆会标明是哪个应用写的，比如 `claude-code`，你随时能把它和你亲口告诉 Suzent 的内容区分开。
- Suzent 会像其他记忆一样把它整理进你的笔记。两者冲突时，以你直接告诉 Suzent 的为准。
- 应用只能新增，不能修改或删除已有的记忆。要更正记忆，请直接告诉 Suzent。

## 教应用什么时候用记忆

这些工具装好就能用，但装一个 skill 可以告诉应用什么时候该查、什么时候该存。
给 Claude Code 安装：

```bash
suzent mcp skill --dir ~/.claude/skills
```

Codex 用 `--dir ~/.codex/skills`。不带 `--dir` 运行 `suzent mcp skill` 会直接打印 skill 内容，
你可以把它粘贴到应用存放说明的地方。

## 常见问题

**提示 "Cannot connect to Suzent server"**：先启动 Suzent，打开应用或运行 `suzent start`。

**提示 "Writing memories from other agents is off"**：在 **设置 → 记忆系统 → 其他 agent**
里打开 **允许它们保存记忆**。

**应用提示找不到 `suzent`**：应用看不到 `suzent` 命令，请改用完整路径。在终端里运行
`which suzent`（macOS 和 Linux）或 `where suzent`（Windows）可以查到。

其他电脑上的应用暂时还不能连接，这个服务器只和同一台电脑上的 Suzent 通信。
