---
sidebar_position: 12
title: Xiaomi MiMo
description: Use Xiaomi MiMo models, pay as you go or on a Token Plan.
---

# Xiaomi MiMo

Use Xiaomi MiMo models through their OpenAI-compatible API, pay as you go or on a Token Plan.

## Set up

1. Get an API key from the Xiaomi MiMo developer console.
2. Open **Settings → Providers**. Under **Add a provider**, find **Xiaomi MiMo**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Xiaomi MiMo then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Pay as you go** | `https://api.xiaomimimo.com/v1` |
| **Token Plan · China** | `https://token-plan-cn.xiaomimimo.com/v1` |
| **Token Plan · Singapore** | `https://token-plan-sgp.xiaomimimo.com/v1` |
| **Token Plan · Europe** | `https://token-plan-ams.xiaomimimo.com/v1` |

**Custom URL** lets you type any other address, such as a proxy.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `XIAOMI_MIMO_API_KEY` | |
| **Base URL** | `XIAOMI_MIMO_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
