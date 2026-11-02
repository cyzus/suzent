---
sidebar_position: 8
title: MiniMax
description: Use MiniMax models with a MiniMax API key.
---

# MiniMax

Use MiniMax models with an API key from the MiniMax platform.

## Set up

1. Get an API key from [platform.minimaxi.com](https://platform.minimaxi.com/).
2. Open **Settings → Providers**. Under **Add a provider**, find **MiniMax**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Region** (see [region choices](#region-choices)),
   then paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and MiniMax then moves up to the providers you
have set up.

## Region choices

Pick the region your key was created for. It decides where Suzent sends requests.

| Region | Base URL |
|---|---|
| **China** | `https://api.minimaxi.com/v1` |
| **Global** | `https://api.minimax.io/v1` |

**Custom URL** lets you type any other address, such as a proxy.

China and Global accounts are separate, so a key from one won't work with the other.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `MINIMAX_API_KEY` | |
| **Base URL** | `MINIMAX_BASE_URL` | Filled in by your **Region** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
