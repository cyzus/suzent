---
sidebar_position: 6
title: Qwen (DashScope)
description: Use Qwen models with a pay-as-you-go Alibaba Cloud Model Studio (Bailian) API key.
---

# Qwen (DashScope)

Use Qwen models with a pay-as-you-go API key from Alibaba Cloud Model Studio (Bailian).

## Set up

1. Get an API key from [bailian.console.aliyun.com](https://bailian.console.aliyun.com/).
2. Open **Settings → Providers**. Under **Add a provider**, find **Qwen (DashScope)**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Region** (see [region choices](#region-choices)),
   then paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Qwen (DashScope) then moves up to the providers you
have set up.

## Region choices

Pick the region your key was created for. It decides where Suzent sends requests.

| Region | Base URL |
|---|---|
| **China** | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **International** | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |

**Custom URL** lets you type any other address, such as a proxy.

China and Global accounts are separate, so a key from one won't work with the other.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `DASHSCOPE_API_KEY` | |
| **Base URL** | `DASHSCOPE_BASE_URL` | Filled in by your **Region** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.

## Good to know

Have a Bailian Token Plan or Coding Plan subscription instead? Use [Bailian Plan](./bailian-plan.md).
