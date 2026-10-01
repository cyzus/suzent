---
sidebar_position: 9
title: Moonshot (Kimi)
description: Use Kimi models with a Moonshot API key.
---

# Moonshot (Kimi)

Use Kimi models, known for long context, with an API key from Moonshot.

## Set up

1. Get an API key from [platform.moonshot.cn](https://platform.moonshot.cn).
2. Open **Settings → Providers → Moonshot (Kimi)**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `MOONSHOT_API_KEY` | Starts with `sk-`. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.
