---
sidebar_position: 1
title: Ollama
description: Run models entirely on your own computer with Ollama, with no API key and no internet connection.
---

# Ollama

Ollama runs models entirely on your computer. You need no API key, and nothing
you say leaves your machine.

## Set up

1. Install Ollama from [ollama.com](https://ollama.com) and pull a model:

   ```bash
   ollama pull llama3.2
   ```
2. Open **Settings → Providers**. Under **Add a provider**, find **Ollama**
   (or type its name in the search box) and click it to open its card.
3. Click **Test connection & fetch models** to list the models you have pulled,
   then tick the ones you want on the **Models** tab.

Changes save on their own.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Base URL** | `OLLAMA_BASE_URL` | Change it only if Ollama isn't running at `http://localhost:11434`. |
| **API Key (Optional)** | `OLLAMA_API_KEY` | Only if your Ollama server requires one. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

The agent relies on tool calling, so choose a model that supports tools. Small
local models work well for the **Cheap** [model role](../model-roles.md) even
if you keep a cloud model for your main conversations.

Ollama's hosted models need an account and a key; use [Ollama Cloud](../cloud/ollama-cloud.md) for those.
