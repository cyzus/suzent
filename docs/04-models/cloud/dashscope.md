---
sidebar_position: 8
title: DashScope (Alibaba Cloud)
description: Use Qwen models through Alibaba Cloud Model Studio (Bailian).
---

# DashScope (Alibaba Cloud)

Use Qwen models through Alibaba Cloud Model Studio (Bailian).

## Set up

1. Get an API key from [bailian.console.aliyun.com](https://bailian.console.aliyun.com).
2. Open **Settings → Providers → Dashscope**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `DASHSCOPE_API_KEY` |  |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.

## Good to know

Suzent connects to the mainland China endpoint, `https://dashscope.aliyuncs.com/compatible-mode/v1`.
