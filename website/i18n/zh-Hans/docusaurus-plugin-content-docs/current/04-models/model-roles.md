---
sidebar_position: 1
title: 模型角色
description: 决定每类工作由哪个模型负责，从日常对话到记忆、图像和语音。
---

# 模型角色

不是每项工作都需要最大的模型。**设置 → 模型角色** 让你为不同类型的工作分配模型，这样日常的后台工作可以交给小而便宜的模型，而对话使用你最好的模型。

| 角色 | 用途 | 留空时 |
|---|---|---|
| **主要** | 你的对话。需要支持工具调用和较大的上下文窗口。 | 必填 |
| **轻量** | 轻量后台工作的默认模型。小而快的模型最合适。 | 使用主要模型 |
| **标题** | 为对话生成标题。 | 使用轻量模型 |
| **记忆提取** | 每轮对话后挑出值得记住的事实。 | 使用轻量模型 |
| **决策** | 快速的是非判断：[目标](../03-features/automation.md#goal-mode)是否完成，以及某个工具调用能否[自动批准](../03-features/tools/human-in-the-loop.md)。 | 使用轻量模型 |
| **目标判断**、**权限审批** | 只为其中一种判断单独指定模型，位于 **高级决策角色** 中。 | 使用决策模型 |
| **Dream** | 夜间的[记忆整理](../03-features/memory/README.md#how-memory-is-tidied)。 | 使用主要模型 |
| **视觉** | 识别图片。 | 使用主要模型（需支持视觉） |
| **向量嵌入** | 记忆搜索。 | 无，需先分配才能使用记忆搜索 |
| **图像生成**、**图像编辑**、**视频生成**、**语音合成** | [创作类工具](../03-features/tools/media.md)。 | 无，需先分配才能使用对应工具 |
| **快速决策模型** | 可选。用[决策模型](#decision-models)判断 [Mailbox](../03-features/mailbox.md) 中新类型事件的去向。 | 由「决策」完成 |

<a id="decision-models"></a>

## 决策模型

决策模型不写文字，只从固定选项中选择，并给出有多确定。几百毫秒就能完成，成本只有聊天模型的一小部分。Suzent 可以使用：

- **OpenAI**：`openai/gpt-6-luna`，通过 OpenAI 的 Decisions API。
- **Gemini**：`gemini/gemini-decision-1`，通过 Gemini Decisions API。
- **你自己运行的 LiteLLM proxy**：使用它提供的决策模型，例如 Cloudflare、Databricks 的，写作 `litellm_proxy/<model>`。
- **TypeSafe 的 Jev 或自己部署的决策模型**：只要使用 System One 协议，就可以作为自定义提供商添加（见[模型能力](../08-developing/architecture/model-capabilities.md#decision-models)）。

每种都使用你在 **设置 → 提供商** 中为对应提供商设置的 key 和地址。在 **设置 → 模型角色** 的 **快速决策模型** 中选择一个即可。目前它用于判断 Mailbox 中每种新类型事件第一次到达时的去向。不够确定时，事件交给 Regent，且不保存规则，下次同类事件会重新判断。调用失败或没有设置时，由 **决策** 角色完成。

决策模型不能聊天，所以不会出现在其他角色的选项里。

<a id="backups"></a>

## 备用模型

每个角色还可以设置备用模型。第一个失败时，Suzent 会按顺序尝试下一个。
