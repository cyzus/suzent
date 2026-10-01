---
sidebar_position: 5
title: Google Gemini
description: Use Gemini models with a Google AI Studio API key, including the free tier.
---

# Google Gemini

Use Gemini models with an API key from Google AI Studio. A free tier is available.

## Set up

1. Get an API key from [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
2. Open **Settings → Providers → Google Gemini**, click **CHANGE** on the **API KEYS** tab, and paste the key.
3. On the **MODELS** tab, click **FETCH**, tick the models you want, and click **Save Changes**.

## Settings

| Field | Environment variable | Notes |
|---|---|---|
| **API Key** | `GEMINI_API_KEY` | Starts with `AIza`. `GOOGLE_API_KEY` also works. |

You can set the key's environment variable before starting Suzent instead of
pasting it. It then shows as **Set in env** and can't be changed from the app.

