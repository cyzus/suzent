---
sidebar_position: 13
title: OpenRouter
description: Reach hundreds of models from many providers with one OpenRouter key.
---

# OpenRouter

Reach hundreds of models (GPT, Claude, Gemini, Llama, Mistral, and more) with a single key. Handy for trying models without opening an account with each provider.

## Set up

1. Get an API key from [openrouter.ai/keys](https://openrouter.ai/keys).
2. Open **Settings → Providers → OpenRouter**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `OPENROUTER_API_KEY` | Starts with `sk-or-`. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.

## Good to know

**FETCH** loads OpenRouter's full catalog, so tick only the models you plan to use.
