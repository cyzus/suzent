---
sidebar_position: 4
title: Anthropic
description: Use Claude models with an Anthropic API key.
---

# Anthropic

Use Claude models with an API key from the Anthropic Console.

## Set up

1. Get an API key from [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
2. Open **Settings → Providers → Anthropic**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `ANTHROPIC_API_KEY` | Starts with `sk-ant-`. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.
