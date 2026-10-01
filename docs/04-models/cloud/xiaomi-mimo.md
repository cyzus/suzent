---
sidebar_position: 12
title: Xiaomi MiMo
description: Use Xiaomi MiMo models through their OpenAI-compatible API.
---

# Xiaomi MiMo

Use Xiaomi MiMo models through their OpenAI-compatible API.

## Set up

1. Get an API key from the Xiaomi MiMo developer console.
2. Open **Settings → Providers → Xiaomi MiMo**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `XIAOMI_MIMO_API_KEY` |  |
| **Base URL (Optional)** | — | Defaults to `https://api.xiaomimimo.com/v1`. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.
