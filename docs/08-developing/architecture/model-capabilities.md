---
sidebar_position: 9
title: Model capabilities and roles
---

# Model capabilities and roles

This page is for contributors. For choosing providers and assigning model roles
as a user, see [Models & Providers](../../04-models/README.md).

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
and via a periodic LiteLLM sync that refreshes context windows
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

### Image editing

The registry preserves LiteLLM's `supported_endpoints` and `image_edit` mode.
A model is confirmed to support editing when its endpoints include
`/v1/images/edits` or its mode is `image_edit`. Missing metadata means unknown,
not unsupported; some providers' endpoint lists are incomplete. Runtime sync and
`scripts/sync_model_capabilities.py` use the same parser. Bare OpenAI model IDs
are normalized to the `openai/` prefix used by Suzent.

Configure **Image Editing** separately in Settings → Model Roles. Confirmed
models appear as suggestions; enabled models with unknown editing capability
remain available as explicit overrides. There is no chat-model fallback.

The `edit_image` tool accepts a prompt, local `image_paths`, optional PNG
`mask_path`, `size`, `quality`, and `count` (1–4). Each input is limited to 20 MB;
providers can impose stricter limits. Mask dimensions must match the source.
Multi-image, mask, dimensions, and quality support depend on the selected model.
Results are saved as new files in the workspace's `images` directory; pass the
returned `saved_paths` to edit them again. Existing chats with a saved tool
selection may need **ImageEditTool** enabled.

`generate_image` passes size and quality to the image API and requests the count
as a native batch. DALL-E 3 therefore requires count=1. Its free-form `style`
remains a prompt hint. Both tools save all returned images with extensions
identified from the image bytes and report empty provider responses as errors.

When a provider does not support `quality`, image tools omit that optional hint
and report `dropped_params: ["quality"]` along with a note in the result.
Unsupported size, mask, and batch-count parameters still fail explicitly.

## Model role inheritance

Settings → Model Roles assigns models by task. An empty task role inherits the
nearest configured parent, including its ordered model list:

```text
primary
├── cheap
│   ├── title
│   ├── suggestion
│   ├── memory_extraction
│   └── decision
│       ├── goal_judge
│       └── permission_review
└── dream
```

- `title`: conversation titles.
- `suggestion`: next-message prediction for the composer's ghost text
  (`POST /chat/input-suggestion`; the client sends its recent messages because
  the turn's final save can land after the stream ends). With `chat_id` and
  `reply_key` the prediction is stored in the `input_suggestions` table, and
  `GET /chat/input-suggestion?chat_id=` returns it so any device can restore it
  while the chat's last reply still matches `reply_key`.
- `memory_extraction`: extract durable facts from conversations.
- `decision`: shared default for goal completion and automatic permission review.
- `goal_judge` / `permission_review`: optional overrides under Advanced decision roles.
- `dream`: memory consolidation and knowledge-vault lint passes.

Explicit assignments replace inheritance; clearing a task role restores it, including
after restart when YAML defines a default. Saving roles updates the running memory
extractor immediately; an extraction already in progress keeps its original client.
Inheritance selects configuration, not a second retry path after a model fails.
Individual callers retain their existing retry behavior. Context compaction still
uses the conversation model.

Existing `cheap` configurations continue to serve title, extraction, and decision
tasks. A saved role assignment takes precedence over YAML role defaults. The legacy
`memory_consolidation_model` setting supplies the initial Dream assignment when
no explicit `dream` role exists; Dream otherwise inherits Primary. An explicitly cleared Dream role remains empty on restart, even when the legacy
setting is still present.

Vision retains its capability-filtered inheritance from Primary. Embedding, image
generation, and TTS require explicit specialist models and have no parent role.

## Provider registry

Built-in providers are declared in `config/providers.json`. User-defined
providers are merged from `config/providers.user.json` and appear alongside the
built-in cards after the registry reloads. The ChatGPT Subscription provider
(`chatgpt/...` model IDs) authenticates through LiteLLM's ChatGPT device-code
flow; its tokens live in Suzent's local config directory and are never returned
by the HTTP status endpoint.

## Prompt caching

Every provider caches a request prefix: tool definitions, then the system
prompt, then the history. Anything that changes early in that order makes the
provider re-read everything after it at full price, so the runtime keeps the
prefix byte-identical from one request to the next:

- **Core memory is pinned per chat.** The system prompt carries the core-memory
  version the chat started with (`memory/core_memory_pin.py`). Later edits to
  persona, user, `MEMORY.md` or the project's `context.md` reach the model once,
  as a diff in a system reminder on the next turn, which lands after the cached
  history. A diff counts as seen only if it survives the reminder budget;
  otherwise it is offered again next turn. The pin follows the live files only when that costs nothing extra: a
  chat with no reply yet, after compaction, after a restart, or when the diff is
  larger than `MAX_DIFF_CHARS`. Pins are keyed by chat and user and never held on
  the shared agent instance.
- **Tool-result trimming moves in steps.** `ToolResultTrimmer` trims results
  older than a boundary that advances `TRIM_STEP` messages at a time, and
  trimming an already trimmed result is a no-op. The trimmed history is what the
  run persists, so most turns resend the earlier prefix unchanged. A hard clear
  keeps the exact cutoff: it runs at the compaction threshold, where freeing
  space matters more than the cache.
- **Discovered tools depend on the provider profile.** With the local
  `search_tools` fallback, pydantic-ai adds a discovered tool's definition to the
  `tools` array on providers whose profile has no `tool_addition_mode` (Gemini,
  Chat Completions, OpenAI-compatible endpoints), which invalidates the whole
  prefix once per discovery. First-party OpenAI Responses, including ChatGPT,
  uses `with_definitions` and appends the definition after the history instead.
  Closing the gap for the other providers needs an upstream wire format, or
  sending every deferred schema up front.
