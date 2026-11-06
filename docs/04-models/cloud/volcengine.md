---
sidebar_position: 15
title: Volcengine Ark
description: Use Volcengine Ark's Coding Plan, Agent Plan, or pay-as-you-go models.
---

# Volcengine Ark

Use Doubao and the other models on Volcengine Ark (ByteDance), through the Coding Plan, the Agent Plan, or pay as you go.

## Set up

1. Get an API key from [console.volcengine.com/ark](https://console.volcengine.com/ark).
2. Open **Settings → Providers**. Under **Add a provider**, find **Volcengine Ark**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Volcengine Ark then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Coding Plan** | `https://ark.cn-beijing.volces.com/api/coding/v3` |
| **Agent Plan** | `https://ark.cn-beijing.volces.com/api/plan/v3` |
| **Pay as you go** | `https://ark.cn-beijing.volces.com/api/v3` |

**Custom URL** lets you type any other address, such as a proxy.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `VOLCENGINE_API_KEY` | |
| **Base URL** | `VOLCENGINE_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
