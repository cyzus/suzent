---
sidebar_position: 4
title: LiteLLM Proxy
description: Route Suzent through your own LiteLLM proxy for shared keys, rate limits, and cost tracking.
---

# LiteLLM Proxy

If you already run a [LiteLLM](https://docs.litellm.ai) proxy in front of your
models, for example to share keys across a team or track spending, Suzent can
use it like any other provider.

## Set up

1. Start your LiteLLM proxy and note its URL and master key.
2. Open **Settings → Providers → LiteLLM Proxy** and fill in both fields.
3. On the **MODELS** tab, click **FETCH** to load the models your proxy
   exposes, tick the ones you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **Master Key** | `LITELLM_MASTER_KEY` | `LITELLM_PROXY_API_KEY` also works. |
| **Base URL** | — | For example `http://localhost:4000`. |

You can set the master key's environment variable before starting Suzent
instead of pasting it. It then shows as **Set in env** and can't be changed
from the app.
