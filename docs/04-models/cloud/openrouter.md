---
sidebar_position: 19
title: OpenRouter
description: Reach hundreds of models from many providers with one OpenRouter key.
---

# OpenRouter

Reach hundreds of models (GPT, Claude, Gemini, Llama, Mistral, and more) with a single key. Handy for trying models without opening an account with each provider.

## Set up

1. Get an API key from [openrouter.ai/keys](https://openrouter.ai/keys).
2. Open **Settings → Providers**. Under **Add a provider**, find **OpenRouter**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and OpenRouter then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `OPENROUTER_API_KEY` | Starts with `sk-or-`. |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

Fetching loads OpenRouter's full catalog, so tick only the models you plan to use.
