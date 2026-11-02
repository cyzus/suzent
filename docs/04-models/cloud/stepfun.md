---
sidebar_position: 16
title: StepFun
description: Use StepFun's Step models on the Step Plan or pay as you go.
---

# StepFun

Use StepFun's Step models, on the Step Plan or pay as you go.

## Set up

1. Get an API key from [platform.stepfun.com/interface-key](https://platform.stepfun.com/interface-key).
2. Open **Settings → Providers**. Under **Add a provider**, find **StepFun**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, pick your **Plan** (see [plan choices](#plan-choices)),
   then paste the key and click **Save**.
4. Click **Test connection & fetch models**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and StepFun then moves up to the providers you
have set up.

## Plan choices

Pick the plan your key was created for. It decides where Suzent sends requests.

| Plan | Base URL |
|---|---|
| **Step Plan · China** | `https://api.stepfun.com/step_plan/v1` |
| **Pay as you go · China** | `https://api.stepfun.com/v1` |
| **Step Plan · Global** | `https://api.stepfun.ai/step_plan/v1` |
| **Pay as you go · Global** | `https://api.stepfun.ai/v1` |

**Custom URL** lets you type any other address, such as a proxy.

China and Global accounts are separate, so a key from one won't work with the other.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `STEPFUN_API_KEY` | |
| **Base URL** | `STEPFUN_BASE_URL` | Filled in by your **Plan** choice; shown only for **Custom URL**. |

You can set these environment variables before starting Suzent instead of typing the values in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
