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

The extraction model runs once per exchange, so a small fast model is the right choice
here. Leave it unset to use the default chat model.

These settings change *how* memory works. To change *what* Suzent remembers, edit
the notes in `MEMORY.md` instead; see
[MEMORY.md is half yours](https://suzent.com/docs/features/memory#memorymd-is-half-yours).

## Consolidation

How often the dream runs, and how much it takes on. See
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
memory_consolidation_model: null              # Legacy; set the Dream role in Settings → Model Roles instead
memory_consolidation_memory_max_lines: 200    # Size cap on MEMORY.md
```

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

## Sessions and transcripts

```yaml
session_daily_reset_hour: 0        # UTC hour for a daily reset (0 = off)
session_idle_timeout_minutes: 0    # Reset after inactivity (0 = off)
jsonl_transcripts_enabled: true    # Keep a transcript per session
transcript_indexing_enabled: false # Also make transcripts searchable
```

Transcript indexing lets you search across past conversations, not just extracted facts.
It costs storage and embedding calls proportional to everything you say, which is why it
is off by default.

## Context window

```yaml
max_context_tokens: 0              # 0 = use whatever the active model supports
```

Long conversations are compacted automatically once they fill 80% of the
model's context window (`context_compaction_trigger`). A 1M-token model gets a
1M-token budget, a 128k model gets 128k. If Suzent doesn't know a model's window,
it assumes 200k tokens.

Set `max_context_tokens` to a non-zero value to cap that budget, for example to
keep costs down. It can only lower the limit, never raise it.

## Rebuilding the search index

The Markdown files are the real memory; the search index is built from them. If
search starts returning odd results, open the **Memory** panel, view
`MEMORY.md`, and click **Reindex**. Nothing is lost, but a full rebuild
re-embeds every file, so it takes a while and costs embedding calls.
