# Codex Login Session

The Codex Login Session provider lets Suzent use a local ChatGPT/Codex subscription session through the official Codex CLI. It is for users who have signed in with `codex login` and do not want to configure an OpenAI API key.

This provider is separate from the OpenAI API provider:

| Provider | Authentication | Model ID |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `openai/...` |
| Codex Login Session | local Codex CLI ChatGPT login | `codex-subscription/...` |

## Setup

1. Install the official Codex CLI.
2. Run `codex login` in a terminal and choose ChatGPT sign-in.
3. In Suzent, open **Settings -> Providers -> Codex Login Session**.
4. Click **Refresh** and confirm the status is connected.
5. Enable **Codex GPT-5.5 (ChatGPT Login)**.

Suzent never reads or returns Codex token files. The Codex CLI and its local credential store remain the authority for authentication.

## Runtime Behavior

Codex subscription chat turns are routed through `codex exec` using the local login session. The selected Suzent model ID stays distinct from API-key models:

```text
codex-subscription/gpt-5.5
```

Older Codex model selections, such as `codex-subscription/gpt-5.1-codex`, are mapped to `gpt-5.5` for compatibility with current ChatGPT-account Codex CLI behavior.

## Current Limitations

- Codex Login Session currently supports text-only chat turns.
- Attachments and file mentions are not passed to the Codex CLI bridge yet.
- If Codex reports an API-key login instead of a ChatGPT login, run `codex logout`, then `codex login` and choose ChatGPT sign-in.
