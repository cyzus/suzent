---
sidebar_position: 20
title: OpenCode Go
description: Use the models in your OpenCode Go subscription.
---

# OpenCode Go

Use the models included in an OpenCode Go subscription.

## Set up

1. Get an API key from [opencode.ai/auth](https://opencode.ai/auth).
2. Open **Settings → Providers**. Under **Add a provider**, find **OpenCode Go**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and OpenCode Go then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `OPENCODE_GO_API_KEY` | |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
