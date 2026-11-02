---
sidebar_position: 1
title: OpenAI
description: Use GPT models with an OpenAI API key, or point Suzent at Azure OpenAI or another compatible endpoint.
---

# OpenAI

Use GPT and other OpenAI models with an API key from your OpenAI account.

## Set up

1. Get an API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Open **Settings → Providers**. Under **Add a provider**, find **OpenAI**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and OpenAI then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `OPENAI_API_KEY` | Starts with `sk-`. |
| **Base URL (Optional)** | `OPENAI_BASE_URL` | Leave empty for OpenAI. Set it for Azure OpenAI or another OpenAI-compatible endpoint. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

Already pay for ChatGPT Plus or Pro? The [ChatGPT Subscription](./chatgpt-subscription.md) provider uses your plan instead of API credit.
