---
sidebar_position: 22
title: Ollama Cloud
description: Use Ollama's hosted cloud models with an ollama.com API key.
---

# Ollama Cloud

Use the models Ollama hosts in its cloud, with an API key from your ollama.com account.

## Set up

1. Get an API key from [ollama.com/settings/keys](https://ollama.com/settings/keys).
2. Open **Settings → Providers**. Under **Add a provider**, find **Ollama Cloud**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Ollama Cloud then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `OLLAMA_CLOUD_API_KEY` | |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

To run models on your own computer instead, use [Ollama](../local/ollama.md).
