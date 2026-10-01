---
sidebar_position: 2
title: OpenAI
description: Use GPT models with an OpenAI API key, or point Suzent at Azure OpenAI or another compatible endpoint.
---

# OpenAI

Use GPT and other OpenAI models with an API key from your OpenAI account.

## Set up

1. Get an API key from [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
2. Open **Settings → Providers → OpenAI**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `OPENAI_API_KEY` | Starts with `sk-`. |
| **Base URL (Optional)** | — | Leave empty for OpenAI. Set it for Azure OpenAI or another OpenAI-compatible endpoint. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.

## Good to know

Already pay for ChatGPT Plus or Pro? The [ChatGPT Subscription](./chatgpt-subscription.md) provider uses your plan instead of API credit.
