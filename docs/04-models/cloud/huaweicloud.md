---
sidebar_position: 18
title: Huawei Cloud MaaS
description: Use Huawei Cloud MaaS models on the Token Plan or pay as you go.
---

# Huawei Cloud MaaS

Use the models on Huawei Cloud's ModelArts MaaS, on the Token Plan or pay as you go.

## Set up

1. Get an API key from [console.huaweicloud.com/modelarts](https://console.huaweicloud.com/modelarts/?#/model-studio/authmanage).
2. Open **Settings → Providers**. Under **Add a provider**, find **Huawei Cloud MaaS**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Huawei Cloud MaaS then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Token Plan** | `https://api.modelarts-maas.com/plan/v2` |
| **Pay as you go** | `https://api.modelarts-maas.com/openai/v1` |

**Custom URL** lets you type any other address, such as a proxy.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `HUAWEICLOUD_API_KEY` | |
| **Base URL** | `HUAWEICLOUD_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
