---
sidebar_position: 14
title: Tencent Cloud
description: Use Tencent Cloud's Token Plan, Coding Plan, or pay-as-you-go models.
---

# Tencent Cloud

Use Hunyuan and the other models on Tencent Cloud, through a Token Plan, a Coding Plan, an enterprise plan, or pay as you go.

## Set up

1. Get an API key from [console.cloud.tencent.com/tokenhub](https://console.cloud.tencent.com/tokenhub).
2. Open **Settings → Providers**. Under **Add a provider**, find **Tencent Cloud**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Tencent Cloud then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Token Plan** | `https://api.lkeap.cloud.tencent.com/plan/v3` |
| **Coding Plan** | `https://api.lkeap.cloud.tencent.com/coding/v3` |
| **Pay as you go · China** | `https://tokenhub.tencentmaas.com/v1` |
| **Pay as you go · Global** | `https://tokenhub-intl.tencentmaas.com/v1` |
| **Enterprise plan · China** | `https://tokenhub.tencentmaas.com/plan/v3` |
| **Enterprise plan · Global** | `https://tokenhub-intl.tencentmaas.com/plan/v3` |

**Custom URL** lets you type any other address, such as a proxy.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `TENCENT_API_KEY` | |
| **Base URL** | `TENCENT_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
