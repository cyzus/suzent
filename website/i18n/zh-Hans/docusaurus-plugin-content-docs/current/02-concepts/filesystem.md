---
sidebar_position: 5
title: 工作区与沙盒
description: 智能体能访问哪些文件夹、文件保存在哪里、如何在隔离沙盒中运行代码，以及如何撤销一轮对话。
---

# 工作区与沙盒

**主权容器。** 主权智能体运行在由你掌控的空间里。本页的设置精确决定了它能访问哪些文件夹、代码在哪里运行，这些都由你有意授予，而不是从某个平台继承而来。请见[什么才是主权智能体？](https://suzent.com/sovereign)。

## 两种运行方式

| | 主机模式（默认） | 沙盒模式 |
|---|---|---|
| **命令在哪里运行** | 直接在你的电脑上 | 在隔离的 Docker 容器中 |
| **能访问什么** | 只有它的工作区文件夹和你挂载的文件夹 | 只有挂载进容器的文件夹 |
| **需要什么** | 无需额外安装 | Docker Desktop（Windows、macOS）或 Docker Engine（Linux） |

可以在对话设置中为单个对话开启沙盒，也可以在 **设置 → 安全** 中为所有对话开启。

## 文件放在哪里

每个对话都有自己的私有文件夹，另外还有一个所有对话共享的文件夹。两种模式下智能体看到的路径相同：

| 路径 | 说明 |
|---|---|
| `/persistence` | 当前对话自己的文件夹。相对路径都落在这里，所以 `report.md` 就是 `/persistence/report.md`。 |
| `/persistence/uploads` | 你在聊天中附加的文件，或从[聊天应用](./social-messaging.md)发来的文件。 |
| `/shared` | 所有对话共享。记忆也存放在这里。 |
| `/mnt/...` | 你从电脑上挂载的文件夹（见下文）。 |

在磁盘上，它们位于 Suzent 文件夹下的 `.suzent/sandbox/`：每个对话在 `sessions/<chat-id>/`，共享文件夹在 `shared/`。

智能体无法读取这些文件夹之外的内容。像 `/etc/passwd`、`../../secret` 或 Suzent 自身源代码这样的路径都会被拒绝。

## 让智能体访问你的文件夹

想让智能体处理你电脑上的某个文件夹，需要先挂载它。在 `~/.suzent/config/default.yaml` 中为每个文件夹加一行，格式为 `"你电脑上的文件夹:智能体看到的路径"`：

```yaml
sandbox_volumes:
  - "D:/datasets:/data"
  - "C:/Users/you/Documents/MyVault:/mnt/notebook"
```

这样智能体就会把 `D:/datasets/file.csv` 看作 `/data/file.csv`。在主机模式下，Shell 命令可以通过 `$MOUNT_<名称>` 变量访问挂载的文件夹，`$PROJECT_PATH` 和 `$SHARED_PATH` 分别指向当前对话文件夹和共享文件夹。

## 使用沙盒

1. 安装 Docker 并确保它正在运行。
2. 开启沙盒（见上文）。

就这么简单。每个对话第一次运行命令时会获得自己的容器。容器崩溃会自动重启，闲置 30 分钟后自动停止。你的文件保存在自己的电脑上，所以即使容器被停止或删除，文件也不会丢失。

默认容器包含 Python 和 Shell，可以联网，内存上限 512 MB、使用 1 个 CPU。常见调整写在 `~/.suzent/config/default.yaml` 中：

```yaml
sandbox_network: none          # 让沙盒断网
sandbox_image: suzent-sandbox  # Python + Node.js + 常用数据处理包
```

要使用 `suzent-sandbox` 镜像，先在 Suzent 文件夹中构建一次：`docker compose -f docker/sandbox-compose.yml build`。

<details>
<summary>全部沙盒设置</summary>

| 设置 | 默认值 | 作用 |
|---|---|---|
| `sandbox_enabled` | `false` | 为所有对话使用沙盒 |
| `sandbox_image` | `python:3.11-slim` | 使用的 Docker 镜像 |
| `sandbox_network` | `bridge` | `bridge` 允许联网，`none` 禁止联网 |
| `sandbox_idle_timeout_minutes` | `30` | 闲置多久后停止容器 |
| `sandbox_setup_command` | `""` | 容器创建时运行一次的命令，比如安装软件包 |
| `sandbox_env` | `{}` | 额外的环境变量（密钥类变量会被拦截） |
| `sandbox_volumes` | `[]` | 要挂载的文件夹，格式为 `主机路径:容器路径` |
| `shell_denied_env_patterns` | `[]` | 在主机模式下对命令隐藏的环境变量，例如 `OPENAI_*` |

</details>

<a id="undoing-the-last-turn-retry"></a>

## 撤销上一轮（重试）

对回答不满意？点击智能体最后一条回复下方的重试图标（↺），或在聊天应用中发送 `/retry`。Suzent 会回滚这一轮做过的所有改动，然后重新运行你的消息：

- 对话本身，
- 当前对话文件夹中的文件，
- 你挂载的文件夹中的文件。

需要注意两点：

- **只能重试最后一轮**，没有多步撤销。
- **`/shared` 不会回滚**，因为其他对话也在使用它。重要内容请自行备份（或使用 Git）。

Suzent 会在每轮开始前为挂载的文件夹做快照，所以挂载的文件夹很大时，每一轮都会变慢。只挂载智能体真正需要的文件夹。

## 故障排查

| 问题 | 检查什么 |
|---|---|
| 智能体找不到文件 | 在你的电脑上查看 `.suzent/sandbox/sessions/<chat-id>/`。 |
| 报错"Path traversal" | 路径不在允许的文件夹内，先挂载该文件夹。 |
| 挂载的文件夹不见了 | 检查 `sandbox_volumes` 那一行，然后重启 Suzent。 |
| 沙盒无法启动 | 确认 Docker 正在运行（`docker ps`）。 |
| 沙盒里找不到 `node` | 构建并使用 `suzent-sandbox` 镜像（见上文）。 |
| 沙盒无法联网 | 设置 `sandbox_network: bridge`（默认值）。 |
