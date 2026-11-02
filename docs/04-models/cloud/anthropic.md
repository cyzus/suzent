---
sidebar_position: 3
title: Anthropic
description: Use Claude models with an Anthropic API key.
---

# Anthropic

Use Claude models with an API key from the Anthropic Console.

## Set up

1. Get an API key from [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
2. Open **Settings → Providers**. Under **Add a provider**, find **Anthropic**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Anthropic then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `ANTHROPIC_API_KEY` | Starts with `sk-ant-`. |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
