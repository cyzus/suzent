---
sidebar_position: 15
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

2. Open **Settings → Providers → Ollama** and click **FETCH** to list the
   models you have pulled.
3. Tick the models you want and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Base URL** | `OLLAMA_BASE_URL` | Change it only if Ollama isn't running at `http://localhost:11434`. |
| **API Key (Optional)** | `OLLAMA_API_KEY` | Only if your Ollama server requires one. |

## Good to know

The agent relies on tool calling, so choose a model that supports tools. Small
local models work well for the **Cheap** [model role](./model-roles.md) even
if you keep a cloud model for your main conversations.
