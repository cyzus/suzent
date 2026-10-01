---
sidebar_position: 10
title: Zhipu AI (GLM)
description: Use GLM models with a Zhipu AI API key.
---

# Zhipu AI (GLM)

Use GLM models with an API key from Zhipu AI.

## Set up

1. Get an API key from [open.bigmodel.cn](https://open.bigmodel.cn).
2. Open **Settings → Providers → Zhipu AI (GLM)**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `ZAI_API_KEY` | `ZHIPUAI_API_KEY` also works. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.
