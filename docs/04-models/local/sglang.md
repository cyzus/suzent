---
sidebar_position: 3
title: SGLang
description: Connect Suzent to models you serve yourself with SGLang.
---

# SGLang

If you serve models yourself with [SGLang](https://docs.sglang.ai), on your own computer or a
server you control, Suzent can talk to it directly.

## Set up

1. Start the SGLang server with an OpenAI-compatible API.
2. Open **Settings → Providers**. Under **Add a provider**, find **SGLang**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, enter the server's **Base URL** and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Base URL** | `SGLANG_BASE_URL` | Defaults to `http://127.0.0.1:30000/v1`. |
| **API Key (Optional)** | `SGLANG_API_KEY` | Only if you started the server with an API key. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
