---
sidebar_position: 4
title: Google Gemini
description: Use Gemini models with a Google AI Studio API key, including the free tier.
---

# Google Gemini

Use Gemini models with an API key from Google AI Studio. A free tier is available.

## Set up

1. Get an API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Open **Settings → Providers**. Under **Add a provider**, find **Google Gemini**
   (or type its name in the search box) and click it to open its card.
3. On the **API keys** tab, paste the key and click **Save**.
4. Click **Test connection**, then tick the models you want on the
   **Models** tab.

Changes save on their own, and Google Gemini then moves up to the providers you
have set up.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `GEMINI_API_KEY` | Starts with `AIza`. `GOOGLE_API_KEY` also works. |

You can set the environment variable before starting Suzent instead of typing the key in.
Settings then marks the value **Environment**. A value you save in the app
takes priority over it.
