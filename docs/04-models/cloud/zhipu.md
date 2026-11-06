---
sidebar_position: 11
title: Zhipu GLM / Z.ai
description: Use GLM models with a Zhipu (BigModel) or Z.ai API key, pay as you go or on the GLM Coding Plan.
---

# Zhipu GLM / Z.ai

Use GLM models with an API key from Zhipu's BigModel platform in China or from Z.ai outside it. Both pay as you go and the GLM Coding Plan work.

## Set up

1. Get an API key from [open.bigmodel.cn/usercenter/apikeys](https://open.bigmodel.cn/usercenter/apikeys).
2. Open **Settings → Providers**. Under **Add a provider**, find **Zhipu GLM / Z.ai**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Zhipu GLM / Z.ai then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Pay as you go · China** | `https://open.bigmodel.cn/api/paas/v4` |
| **Coding Plan · China** | `https://open.bigmodel.cn/api/coding/paas/v4` |
| **Pay as you go · Global (Z.ai)** | `https://api.z.ai/api/paas/v4` |
| **Coding Plan · Global (Z.ai)** | `https://api.z.ai/api/coding/paas/v4` |

**Custom URL** lets you type any other address, such as a proxy.

China and Global accounts are separate, so a key from one won't work with the other.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `ZAI_API_KEY` | `ZHIPUAI_API_KEY` also works. |
| **Base URL** | `ZAI_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
