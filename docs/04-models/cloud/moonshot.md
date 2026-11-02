---
sidebar_position: 9
title: Kimi (Moonshot)
description: Use Kimi models with a Moonshot API key.
---

# Kimi (Moonshot)

Use Kimi models, known for long context, with a pay-as-you-go API key from Moonshot.

## Set up

1. Get an API key from [platform.moonshot.cn/console/api-keys](https://platform.moonshot.cn/console/api-keys).
2. Open **Settings → Providers**. Under **Add a provider**, find **Kimi (Moonshot)**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Region** (see [region choices](#region-choices)),
   then paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Kimi (Moonshot) then moves up to the providers you
have set up.

## Region choices

Pick the region your key was created for. It decides where Suzent sends requests.

| Region | Base URL |
|---|---|
| **China** | `https://api.moonshot.cn/v1` |
| **Global** | `https://api.moonshot.ai/v1` |

**Custom URL** lets you type any other address, such as a proxy.

China and Global accounts are separate, so a key from one won't work with the other.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `MOONSHOT_API_KEY` | Starts with `sk-`. |
| **Base URL** | `MOONSHOT_BASE_URL` | Filled in by your **Region** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

Subscribed to Kimi's coding plan? Use [Kimi Code](./kimi-code.md) instead.
