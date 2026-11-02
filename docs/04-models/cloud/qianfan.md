---
sidebar_position: 17
title: Baidu Qianfan
description: Use Baidu Qianfan's Token Plan or pay-as-you-go models.
---

# Baidu Qianfan

Use the models on Baidu Qianfan, through a personal or enterprise Token Plan or pay as you go.

## Set up

1. Get an API key from [console.bce.baidu.com/qianfan/resource/token-plan](https://console.bce.baidu.com/qianfan/resource/token-plan).
2. Open **Settings → Providers**. Under **Add a provider**, find **Baidu Qianfan**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Baidu Qianfan then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Token Plan Personal** | `https://qianfan.baidubce.com/v2/tokenplan/personal` |
| **Token Plan Enterprise** | `https://qianfan.baidubce.com/v2/tokenplan/team` |
| **Pay as you go** | `https://qianfan.baidubce.com/v2` |

**Custom URL** lets you type any other address, such as a proxy.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `QIANFAN_API_KEY` | |
| **Base URL** | `QIANFAN_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

Token Plan keys come from the Token Plan page; pay-as-you-go keys come from Baidu Cloud's API key list. **Get a Baidu Qianfan API key** links to the right one for the plan you pick.
