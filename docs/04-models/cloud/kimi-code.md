---
sidebar_position: 10
title: Kimi Code
description: Use your Kimi Code subscription with its own API key.
---

# Kimi Code

Use the models in your Kimi Code subscription, Kimi's coding plan, with the API key from its console.

## Set up

1. Get an API key from [www.kimi.com/code/console](https://www.kimi.com/code/console).
2. Open **Settings → Providers**. Under **Add a provider**, find **Kimi Code**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Region** (see [region choices](#region-choices)),
   then paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Kimi Code then moves up to the providers you
have set up.

## Region choices

Pick the region your key was created for. It decides where Suzent sends requests.

| Region | Base URL |
|---|---|
| **China** | `https://api.kimi.com/coding/v1` |
| **Global** | `https://api.kimi.ai/coding/v1` |

**Custom URL** lets you type any other address, such as a proxy.

China and Global accounts are separate, so a key from one won't work with the other.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `KIMI_CODE_API_KEY` | Starts with `sk-`. |
| **Base URL** | `KIMI_CODE_BASE_URL` | Filled in by your **Region** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

A Kimi Code key only works here. For a pay-as-you-go Moonshot key, use [Kimi (Moonshot)](./moonshot.md).
