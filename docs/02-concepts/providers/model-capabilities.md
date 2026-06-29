---
sidebar_position: 2
title: Model Capabilities
---

# Model Capabilities

Suzent keeps a registry of per-model metadata — context window, capability
flags (vision, function calling, reasoning, prompt caching), and pricing. This
data drives context compression, role routing, cost estimation, and what the UI
shows for each model.

The registry is loaded from three layers, each overlaying the previous one:

| Layer | Path | Tracked in git? | Written by |
|---|---|---|---|
| **1. Shipped defaults** | `config/capabilities/{provider}.json` | Yes | Maintainers (curated) |
| **2. Local overlay** | `<data dir>/capabilities/{provider}.json` | No | Runtime discovery |
| **3. Global overrides** | `config/model_capabilities.json` | Yes | Maintainers (applied last) |

`<data dir>` defaults to `~/.suzent` (override with `SUZENT_DATA_DIR`).

For a model ID present in more than one layer, **the shipped curated entry
wins** over the local overlay — the overlay only supplies models that aren't
shipped. The global override file is applied last and takes precedence over
everything.

## Why the overlay exists

The app discovers models at runtime — when you click **FETCH** for a provider,
and via a periodic [LiteLLM](./litellm.md) sync that refreshes context windows
and pricing. Those writes go to the **local overlay**, never to the tracked
`config/capabilities/` files.

This keeps the repo clean: `suzent update` runs `git pull`, and if runtime
discovery had been writing into tracked files, every update would conflict.
With the overlay, discovered models persist across updates in your data
directory while the shipped files stay pristine. (For safety, `suzent update`
also discards any stale local edits under `config/capabilities/` before
pulling.)

The overlay is auto-generated and safe to delete; it will be repopulated on the
next discovery.

## Developer mode: writing to the repo

If you maintain Suzent and want newly discovered models to land in the tracked
files so you can **commit** them, start the backend in developer mode:

```bash
suzent start --dev      # desktop dev environment
suzent serve --dev      # headless backend only
```

In dev mode the CLI sets `SUZENT_CAPABILITIES_TO_REPO=1`, which redirects all
runtime capability writes (FETCH discovery, LiteLLM sync, stale-model pruning)
into `config/capabilities/` instead of the overlay. Run a provider FETCH or let
the sync run, review the diff, then commit the curated additions.

Without `--dev` (the default for normal use and production builds), writes go to
the overlay and the repo is never touched.

## Adding a model by hand

To curate a model permanently, add it to its provider file in
`config/capabilities/`. The minimal entry is just a `mode`; fill in the rest to
improve context-window and cost accuracy:

```json
{
  "models": {
    "anthropic/claude-opus-4-8": {
      "mode": "chat",
      "max_input_tokens": 200000,
      "max_output_tokens": 32000,
      "supports_vision": true,
      "supports_function_calling": true,
      "supports_reasoning": true,
      "supports_prompt_caching": true,
      "supports_response_schema": true
    }
  }
}
```

`mode` is one of `chat`, `embedding`, `image_generation`, or `tts`. Keys
starting with `_` (e.g. `_doc`) are treated as comments and ignored.
