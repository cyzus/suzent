---
sidebar_position: 4
title: LiteLLM Proxy
description: Route Suzent through your own LiteLLM proxy for shared keys, rate limits, and cost tracking.
---

# LiteLLM Proxy

If you already run a [LiteLLM](https://docs.litellm.ai) proxy in front of your
models, for example to share keys across a team or track spending, Suzent can
use it like any other provider.

## Set up

1. Start your LiteLLM proxy and note its URL and master key.
2. Open **Settings → Providers**. Under **Add a provider**, find **LiteLLM Proxy**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, fill in **Base URL** and **Master Key**, clicking
   **Save** for each.
4. Click **Test connection** to load the models your proxy
   exposes, then tick the ones you want on the **Models** tab.

Changes save on their own.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Master Key** | `LITELLM_MASTER_KEY` | `LITELLM_PROXY_API_KEY` also works. |
| **Base URL** | `LITELLM_BASE_URL` | For example `http://localhost:4000`. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
