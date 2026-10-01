---
sidebar_position: 7
title: DeepSeek
description: Use DeepSeek chat and reasoning models with a DeepSeek API key.
---

# DeepSeek

Use DeepSeek's low-cost chat and reasoning models.

## Set up

1. Get an API key from [platform.deepseek.com/api_keys](https://platform.deepseek.com/api_keys).
2. Open **Settings → Providers → DeepSeek**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `DEEPSEEK_API_KEY` | Starts with `sk-`. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.

## Good to know

The reasoning model is slower but stronger on multi-step problems.
