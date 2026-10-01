---
sidebar_position: 3
title: 更新
description: 如何更新 Suzent、修复快捷方式，以及跨版本升级已有安装时需要注意什么。
---

# 更新 Suzent

## 更新到最新版本

```bash
suzent update
```

这会把 Suzent 和桌面应用一起更新到同一个经过测试的版本。如果更新过程中出现问题，Suzent 会自动恢复到更新前的版本。如果更新途中电脑断电或被强制关机，请运行 `suzent repair`。

如果你是从源码仓库安装的 Suzent（用于开发），`suzent update` 会改为跟随最新的开发版本。

每个版本的具体改动见[更新日志](https://github.com/cyzus/suzent/blob/main/CHANGELOG.md)。

## 修复应用快捷方式

每次安装和更新都会创建或修复 Suzent 在开始菜单（Windows）、应用程序文件夹（macOS）或应用菜单（Linux）中的入口。想手动修复，或调整快捷方式出现的位置：

```bash
suzent shortcuts                    # 修复
suzent shortcuts --desktop          # 同时添加桌面快捷方式
suzent shortcuts --no-menu          # 移除菜单入口
suzent shortcuts --remove           # 移除 Suzent 创建的所有快捷方式
```

你的选择会在之后的更新中被记住。

## 从旧版本升级

全新安装无需关注这一部分。如果你在升级已有的安装，请找到你当前的版本，阅读之后每个版本的说明。

### v0.10.0 之前：记忆升级

0.10.0 版本改变了记忆的存储和整理方式。大部分工作会自动完成，但有几点值得了解。

**第一次运行会更慢，并消耗更多向量嵌入调用。** Suzent 会重建一次记忆搜索索引，重新读取所有每日日志和笔记本页面。如果你的向量嵌入按次计费，预计会有一笔与记忆总量成正比的一次性开销。

**删除旧的笔记本文件夹前先检查。** 如果你把笔记本移到了自己的文件夹（例如一个 Obsidian 知识库），`~/.suzent/notebook` 下的默认笔记本文件夹里可能仍有真实页面，它们是在某次找不到你的知识库时写入的。这个文件夹看起来像是空的残留物，删除前请先和你真正的知识库对比。

**很早的记忆可能只存在于搜索索引中。** 如果你在记忆改为 Markdown 存储之前就在用 Suzent，有些记忆在别处没有副本，请不要删除它们。在关闭 Suzent 的情况下，从 Suzent 文件夹运行下面的命令，查看有多少条，并把它们复制到每日日志中：

```bash
python scripts/retire_legacy_rows.py            # 只报告
python scripts/retire_legacy_rows.py --export   # 保存到每日日志
```

**已有的 `MEMORY.md` 不会被覆盖。** `MEMORY.md` 现在分为 Suzent 写的部分和你写的部分，用标记注释分隔（见 [MEMORY.md 有一半属于你](../03-features/memory/README.md#memorymd-is-half-yours)）。没有标记的文件会被视为完全由你编写，不会被改动。让一次整理生成新文件，或自己加上标记，就能恢复自动更新。

**前几次 dream 之后笔记本会出现大量改动。** Suzent 会为已有页面添加复查日期和确认计数。如果你的笔记本在 Git 或同步文件夹中，这些改动是正常的。

**搜索结果的排序可能会变化。** 经常被确认的事实和你亲手写下的内容排名更高，过时的内容排名更低。没有任何内容会被删除。

**重复的事实不再写入每日日志。** 只是重复已有记录的事实会被计数，而不是再写一遍。计数保存在 `notebook/.state/confirmations.jsonl` 中。
