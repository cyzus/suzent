---
sidebar_position: 7
title: DeepSeek
description: Use DeepSeek chat and reasoning models with a DeepSeek API key.
---

# DeepSeek

Use DeepSeek's low-cost chat and reasoning models.

## Set up

1. Get an API key from [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys).
2. Open **Settings → Providers**. Under **Add a provider**, find **DeepSeek**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and DeepSeek then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `DEEPSEEK_API_KEY` | Starts with `sk-`. |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

The reasoning model is slower but stronger on multi-step problems.
