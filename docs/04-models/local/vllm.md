---
sidebar_position: 2
title: vLLM
description: Connect Suzent to models you serve yourself with vLLM.
---

# vLLM

If you serve models yourself with [vLLM](https://docs.vllm.ai), on your own computer or a
server you control, Suzent can talk to it directly.

## Set up

1. Start the vLLM server with an OpenAI-compatible API.
2. Open **Settings → Providers**. Under **Add a provider**, find **vLLM**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, enter the server's **Base URL** and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Base URL** | `VLLM_BASE_URL` | Defaults to `http://127.0.0.1:8000/v1`. |
| **API Key (Optional)** | `VLLM_API_KEY` | Only if you started the server with an API key. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
