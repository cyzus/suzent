---
title: 记忆系统
---

# 记忆系统

统一的记忆-会话-智能体架构，具备人类可读的 Markdown 持久化、JSONL 会话记录和可检查的智能体状态。

## 概述

**Markdown 记忆**（`/shared/memory/`）：人类可读的真实来源——每日日志和精选的 MEMORY.md，智能体可通过文件工具直接访问。

**LanceDB 搜索索引**（`.suzent/memory/`）：对提取的事实进行向量 + 全文混合搜索。如有需要可从 Markdown 重建。

**会话记录**（`.suzent/transcripts/`）：每个会话的追加式 JSONL 日志，用于审计和跨会话搜索。

**智能体状态**（`.suzent/state/`）：可检查的 JSON 快照，替代不透明的 pickle 序列化。

## 主要特性

- Markdown 作为真实来源（每日日志 + MEMORY.md）
- 双写：每条事实同时持久化到 Markdown 和 LanceDB
- 语义 + 全文混合搜索
- 基于 LLM 的自动事实提取（简洁的一句话事实）
- 自动汇总核心记忆（刷新 MEMORY.md）
- 压缩前记忆刷新（在上下文压缩前捕获事实）
- JSONL 会话记录，支持可选的记录索引
- JSON v2 智能体状态（人类可读，向后兼容 pickle）
- 会话生命周期管理（每日重置、空闲超时、最大轮次）
- 重要性评分与去重
- 线程安全的智能体工具
- 恢复：通过 `MarkdownIndexer` 从 Markdown 重建 LanceDB

## API 端点

| 端点 | 方法 | 说明 |
|----------|--------|-------------|
| `/memory/core` | GET | 获取核心记忆块 |
| `/memory/core` | PUT | 更新核心记忆块 |
| `/memory/archival` | GET | 搜索归档记忆 |
| `/memory/archival/{id}` | DELETE | 删除某条记忆 |
| `/memory/stats` | GET | 记忆统计信息 |
| `/memory/daily` | GET | 列出每日日志日期 |
| `/memory/daily/{date}` | GET | 获取某日日志内容 |
| `/memory/file` | GET | 获取 MEMORY.md 内容 |
| `/memory/reindex` | POST | 从 Markdown 重建 LanceDB |
| `/session/{id}/transcript` | GET | 获取会话记录 |
| `/session/{id}/state` | GET | 获取智能体状态快照 |
