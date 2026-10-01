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
2. Open **Settings → Providers → vLLM** and enter its base URL.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click
   **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Base URL** | — | Defaults to `http://127.0.0.1:8000/v1`. |
| **API Key (Optional)** | `VLLM_API_KEY` | Only if you started the server with an API key. |
