---
sidebar_position: 21
title: ClinePass
description: Use the models in your ClinePass subscription.
---

# ClinePass

Use the models included in a ClinePass subscription from Cline, such as GLM, Kimi, DeepSeek, Qwen, MiniMax, and MiMo.

## Set up

1. Get an API key from [app.cline.bot](https://app.cline.bot).
2. Open **Settings → Providers**. Under **Add a provider**, find **ClinePass**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and ClinePass then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `CLINEPASS_API_KEY` | |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
