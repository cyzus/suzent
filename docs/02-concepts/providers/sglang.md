---
sidebar_position: 17
title: SGLang
description: Connect Suzent to models you serve yourself with SGLang.
---

# SGLang

If you serve models yourself with [SGLang](https://docs.sglang.ai), on your own computer or a
server you control, Suzent can talk to it directly.

## Set up

1. Start the SGLang server with an OpenAI-compatible API.
2. Open **Settings → Providers → SGLang** and enter its base URL.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click
   **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Base URL** | — | Defaults to `http://127.0.0.1:30000/v1`. |
| **API Key (Optional)** | `SGLANG_API_KEY` | Only if you started the server with an API key. |
