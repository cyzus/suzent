---
sidebar_position: 3
title: Advanced memory settings
description: Tuning options for memory, consolidation, the notebook location, and search.
---

# Advanced memory settings

Most people never open this page. Memory is on out of the box, and the two settings you
are most likely to want — whether it runs at all, and which models it uses — are in
**Settings → Memory System** in the app.

What follows is the tuning that has no UI. Put overrides in `~/.suzent/config/default.yaml`
(machine-specific paths belong in `~/.suzent/config/local.yaml`); both are read after the
shipped `config/default.example.yaml`, so anything you set there wins and survives an
update. Keys are case-insensitive — `MEMORY_ENABLED` and `memory_enabled` are the same
setting.

## The basics

```yaml
memory_enabled: true               # Also the toggle in Settings → Memory System
markdown_memory_enabled: true      # Write facts to /shared/memory/ as Markdown
extraction_model: gemini/gemini-2.5-flash   # "" for heuristic extraction, no model call
user_id: default-user
```

The extraction model runs every few exchanges, so a small fast model is the right choice
here. Leave it unset to use the default chat model.

These settings change *how* memory works. To change *what* Suzent remembers, tell
it in a conversation or edit the notebook pages; see
[Managing what's remembered](https://suzent.com/docs/features/memory#managing-whats-remembered).

## Consolidation

How often the organizer runs, and how much it takes on. See
[How memory is tidied](./README.md#how-memory-is-tidied).

```yaml
memory_consolidation_enabled: true
memory_consolidation_interval_seconds: 1800   # How often to check whether a run is due
memory_consolidation_min_hours: 24            # Minimum wait between runs
memory_consolidation_min_facts: 20            # New facts needed before a run is worth it
memory_consolidation_min_confirmations: 25    # Repeated facts that justify a run on their own
memory_consolidation_max_days: 14             # Days of logs read in one run
memory_consolidation_max_retries: 3           # Attempts before a stuck batch is skipped
memory_consolidation_timeout_seconds: 600
memory_consolidation_model: null              # Legacy; set the Memory organizer role in Settings → Model Roles instead
memory_map_max_lines: 30                      # Size cap on the MEMORY.md map
```

## How facts are picked out

There is nothing to set here. Facts about you are saved only when they are in your own
words, lessons only when the chat shows both the failure and the fix, and facts from
files or pages only with their source.

The notebook audit runs on its own, slower schedule, and only once consolidation is
caught up:

```yaml
memory_lint_enabled: true
memory_lint_min_days: 7
```

## Where the notebook lives

```yaml
notebook_dir: <data-dir>/notebook
```

To use an existing Obsidian vault instead, mount it over `/mnt/notebook`, replacing the
default entry. This takes precedence over `notebook_dir`, which keeps pointing at the
default path. Being machine-specific, it belongs in `~/.suzent/config/local.yaml`:

```yaml
sandbox_volumes:
  - "C:/Users/you/Documents/MyVault:/mnt/notebook"
```

## Search

```yaml
embedding_model: gemini/gemini-embedding-001
embedding_dimension: 3072        # Must match the model; 0 = detect from it
embedding_timeout: 30            # Seconds before a slow provider is given up on
lancedb_uri: <data-dir>/memory
```

Pick the embedding model in **Settings → Memory System** — the list is filtered to what your
configured providers actually offer, so it stays correct as you add or remove keys.

Changing the embedding model means re-embedding everything you have stored: one call per
chunk across your whole memory. It is not a free switch, and the dimension has to change
with it.

## Sessions

```yaml
session_daily_reset_hour: 0        # UTC hour for a daily reset (0 = off)
session_idle_timeout_minutes: 0    # Reset after inactivity (0 = off)
```

## Context window

```yaml
max_context_tokens: 0              # 0 = use whatever the active model supports
```

Long conversations are compacted automatically once they reach 200k tokens or
80% of the model's context window, whichever comes first
(`context_compaction_trigger_tokens`, `context_compaction_trigger`). A 128k model
is compacted at about 102k; a 1M-token model at 200k, so it doesn't pay for
hundreds of thousands of tokens on every message before anything is folded. If
Suzent doesn't know a model's window, it assumes 200k tokens.

Set `max_context_tokens` to a non-zero value to cap that budget, for example to
keep costs down. It can only lower the limit, never raise it.

The summary that replaces older messages is written by the model you are
chatting with, reusing the conversation it has already read, so most of it
comes from the provider's prompt cache and costs a fraction of the normal price.
Once the conversation reaches 100k tokens or half the window, whichever comes
first (`context_precompaction_trigger_tokens`, `context_precompaction_trigger`),
Suzent starts writing the next summary in the background. That happens during a
long run as well as when a reply finishes, so the summary is usually ready
before compaction is due and you don't wait for it. A prepared summary is kept
on disk, so a restart doesn't throw it away.

Providers only keep that cache for a while (Anthropic 5 minutes, OpenAI and
Gemini about 5 minutes, DeepSeek hours). If you come back to a conversation
after its cache has expired and it is still past that size, Suzent sends
the prepared summary instead of the full history, since the full history would
be billed at the normal price again. While the cache is still warm, nothing
changes until compaction is due. Suzent also learns from your own usage: when a
provider still serves the cache after a longer pause, it trusts that longer
lifetime from then on.

When a summary has to be written on a cold cache, Suzent compares the price of
the conversation's model against the memory extraction model and uses the
cheaper one.

### Seeing compaction

In the chat, a compaction shows as a thin divider at the point where it
happened, with the context size before and after. A line under it says when
the summary was prepared in advance, or that it was used because you were away
long enough for the cache to expire. **Show summary** opens what the older
messages were folded into. A failed compaction shows in red and leaves the
history as it was.

The **Context** panel shows when the conversation was last compacted, and
whether the next summary is being prepared or is ready.

Other settings:

- `anthropic_prompt_cache_ttl: 1h` asks Anthropic to keep the cache for an hour
  instead of 5 minutes. Writing to it costs twice the input price instead of
  1.25 times, so it pays off when you often pause between messages.
- `context_precompaction_trigger: 0` turns preparing summaries off.
- `context_compaction_trigger_tokens: 0` and
  `context_precompaction_trigger_tokens: 0` drop the token sizes and use only the
  share of the window.
- `compaction_reuse_prompt_cache: false` has the memory extraction model write
  every summary.

## Rebuilding the search index

The Markdown files are the real memory; the search index is built from them. If
search starts returning odd results, open the **Memory** panel, view
`MEMORY.md`, and click **Reindex**. Nothing is lost, but a full rebuild
re-embeds every file, so it takes a while and costs embedding calls.
