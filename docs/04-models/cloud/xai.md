---
sidebar_position: 5
title: xAI (Grok)
description: Use Grok models with an xAI API key.
---

# xAI (Grok)

Use Grok models with an API key from xAI.

## Set up

1. Get an API key from [console.x.ai](https://console.x.ai/).
2. Open **Settings → Providers**. Under **Add a provider**, find **xAI (Grok)**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and xAI (Grok) then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `XAI_API_KEY` | Starts with `xai-`. |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
