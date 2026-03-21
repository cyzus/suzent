---
title: 文件系统与执行
---

# 文件系统与执行

Suzent 通过两种模式提供安全的文件访问和代码执行：**沙箱模式**（隔离的 Docker 容器）和**主机模式**（带限制的直接执行）。

## 执行模式

| 模式 | BashTool | 文件工具 | 路径风格 |
|------|----------|------------|------------|
| **沙箱** | 在 Docker 容器中运行 | 虚拟文件系统 | `/persistence`、`/shared`、`/mnt/*` |
| **主机** | 在主机上运行 | 主机文件系统 | `$PERSISTENCE_PATH`、`$SHARED_PATH`、`$MOUNT_*` |

在创建对话时，可通过聊天设置面板切换沙箱模式。

---

## 虚拟文件系统（两种模式通用）

| 虚拟路径 | 映射至 | 用途 |
|-------------|---------|---------|
| `/persistence` | `.suzent/sandbox/sessions/{chat_id}/` | 每个对话的独立存储 |
| `/shared` | `.suzent/sandbox/shared/` | 跨对话共享存储 |
| `/uploads` | `.suzent/sandbox/sessions/{chat_id}/uploads/` | 上传的文件 |
| `/mnt/*` | 自定义卷 | 主机目录 |

**相对路径**默认指向 `/persistence`：`data.csv` → `/persistence/data.csv`

### 自定义卷挂载

```yaml
# config/default.yaml
sandbox_volumes:
  - "D:/datasets:/data"
  - "D:/skills:/mnt/skills"
```

这样 `/data/file.csv` 就会映射到主机上的 `D:/datasets/file.csv`。

---

## 沙箱模式

使用 Docker 容器进行隔离执行。每个聊天会话拥有独立的命名容器（`suzent-sandbox-{id}`），首次使用时启动并在会话期间保持运行。

### 特性
- **隔离**：每个会话运行在独立容器中（默认通过 `bridge` 网络访问互联网）
- **数据持久化**：`/persistence` 和 `/shared` 通过绑定挂载自主机——数据在容器重启和删除后仍然保留
- **自动恢复**：容器崩溃时自动重启
- **多语言支持**：Python、Node.js（需自定义镜像）、Shell 命令
- **资源限制**：512 MB 内存、1 CPU、256 进程上限

### 前提条件

- **Docker Desktop**（Windows/macOS）或 Docker Engine（Linux）
- 无需 KVM、特权模式或额外服务

### 配置参考

| 键 | 默认值 | 说明 |
|-----|---------|-------------|
| `sandbox_enabled` | `false` | 启用沙箱模式 |
| `sandbox_image` | `python:3.11-slim` | 使用的 Docker 镜像 |
| `sandbox_network` | `bridge` | 网络模式（`bridge` = 有互联网，`none` = 完全隔离） |
| `sandbox_idle_timeout_minutes` | `30` | 闲置 N 分钟后停止容器 |
| `sandbox_volumes` | `[]` | 额外的绑定挂载（`host:container`） |

---

## 主机模式

直接在主机上执行，但有路径限制。

在主机模式下，可在 Bash 命令中使用以下环境变量：

| 变量 | 指向 |
|----------|-----------|
| `$PERSISTENCE_PATH` | 会话目录 |
| `$SHARED_PATH` | 共享目录 |
| `$MOUNT_SKILLS` | 技能目录 |
| `$MOUNT_*` | 其他挂载卷 |

---

## 文件工具

### ReadFileTool
读取文件，支持自动格式转换（文本、PDF、DOCX、XLSX、图片 OCR）。

### WriteFileTool
创建或覆盖文件。

:::warning
会覆盖整个文件。小修改请使用 `EditFileTool`。
:::

### EditFileTool
精确替换文件中的文本片段。

### GlobTool
按模式查找文件（如 `**/*.py`）。

### GrepTool
用正则表达式搜索文件内容。

---

## 安全

所有路径均经过验证，防止目录遍历攻击：

- ✅ `/persistence/data.csv`
- ✅ `/shared/model.pt`
- ✅ `/data/file.txt`（已挂载时）
- ❌ `/etc/passwd`
- ❌ `../../../secret`
- ❌ 项目源码目录（主机模式下）

---

## 故障排查

| 问题 | 解决方案 |
|-------|----------|
| **文件未找到** | 检查主机上的 `.suzent/sandbox/sessions/{chat_id}/` |
| **路径遍历错误** | 确保路径在允许的目录范围内 |
| **卷无法访问** | 检查配置中的 `sandbox_volumes` |
| **容器启动失败** | 确认 Docker Desktop 正在运行（`docker ps`） |
| **找不到 Node.js** | 构建自定义镜像：`docker compose -f docker/sandbox-compose.yml build`，并设置 `sandbox_image: suzent-sandbox` |
