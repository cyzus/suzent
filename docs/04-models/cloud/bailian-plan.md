---
sidebar_position: 13
title: Bailian Plan
description: Use an Alibaba Cloud Bailian Token Plan or Coding Plan subscription.
---

# Bailian Plan

Use a Bailian Token Plan or Coding Plan subscription from Alibaba Cloud. One plan covers Qwen and other popular models such as GLM, Kimi, and MiniMax.

## Set up

1. Get an API key from [bailian.console.aliyun.com](https://bailian.console.aliyun.com/).
2. Open **Settings → Providers**. Under **Add a provider**, find **Bailian Plan**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Bailian Plan then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Token Plan · Beijing** | `https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1` |
| **Token Plan · Singapore** | `https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1` |
| **Qwen Token Plan (Qwen AI platform)** | `https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1` |
| **Coding Plan** | `https://coding.dashscope.aliyuncs.com/v1` |

**Custom URL** lets you type any other address, such as a proxy.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Plan API Key** | `BAILIAN_PLAN_API_KEY` | The plan's own key, starting with `sk-sp-`. A pay-as-you-go key won't work here. |
| **Base URL** | `BAILIAN_PLAN_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

Paying as you go instead of on a plan? Use [Qwen (DashScope)](./dashscope.md).
