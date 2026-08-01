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

This keeps the repo clean: stable `suzent update` checks out an exact release,
while `suzent update --dev` fast-forwards `main`. If runtime discovery had been
writing into tracked files, either update could conflict. With the overlay,
discovered models persist across updates in your data directory while the
shipped files stay pristine. For safety, the updater discards stale local edits
under `config/capabilities/` before changing revisions.

The overlay is auto-generated and safe to delete; it will be repopulated on the
next discovery.

## Updating the repository data

Developer mode follows the same rule as normal runtime: provider **FETCH**,
LiteLLM sync, and stale-model pruning write to the local overlay. Running
`suzent start --dev` therefore does not modify tracked capability files.

If you maintain Suzent and want to refresh the tracked files, use the dedicated
maintenance command:

```bash
uv run python scripts/sync_model_capabilities.py --to-repo
```

This explicitly enables `SUZENT_CAPABILITIES_TO_REPO=1` for that process.
Review the generated diff before committing it. The scheduled
**Update Model Capabilities** workflow uses this command to open or update a
dedicated pull request.

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
