---
sidebar_position: 6
title: xAI (Grok)
description: Use Grok models with an xAI API key.
---

# xAI (Grok)

Use Grok models with an API key from xAI.

## Set up

1. Get an API key from [console.x.ai](https://console.x.ai).
2. Open **Settings → Providers → xAI (Grok)**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `XAI_API_KEY` | Starts with `xai-`. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.
