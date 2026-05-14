# ChatGPT Subscription

The ChatGPT Subscription provider lets Suzent use models available through a local ChatGPT sign-in flow instead of an OpenAI API key. It is intended for users who have ChatGPT/Codex subscription access and want Suzent to authenticate through the same account-backed flow.

This provider is separate from the OpenAI API provider:

| Provider | Authentication | Model ID |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `openai/...` |
| ChatGPT Subscription | ChatGPT device-code sign-in | `chatgpt/...` |

## Setup

1. Open **Settings -> Providers -> ChatGPT Subscription**.
2. Click **Sign in**.
3. Open the verification URL and enter the device code shown in Suzent.
4. Return to Suzent after the provider reports that it is connected.
5. Enable the `chatgpt/...` models you want to use.

Suzent does not require an OpenAI API key for this provider. ChatGPT auth tokens are managed by LiteLLM's ChatGPT authentication layer in Suzent's local config directory and are not returned by the HTTP status endpoint.

## Runtime Behavior

Chat turns use the normal Suzent agent runtime and pydantic-ai model factory, with model IDs such as:

```text
chatgpt/gpt-5.5
```

The provider can fetch available models after sign-in and stores the enabled model IDs in the same provider configuration used by the rest of Suzent.

## Current Limitations

- The provider depends on LiteLLM's ChatGPT subscription support.
- If sign-in expires, disconnect and sign in again from **Settings -> Providers**.
