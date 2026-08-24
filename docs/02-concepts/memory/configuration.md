# Memory Configuration

All memory settings live in `config/default.yaml`. Every one has a working default —
memory runs without configuring anything.

## Turning memory on

```yaml
MEMORY_ENABLED: true
```

That's the only setting most installs need. Everything below is tuning.

## What gets captured

```yaml
markdown_memory_enabled: true      # Write facts to /shared/memory/ as Markdown
extraction_model: gpt-4o-mini      # Model that picks facts out of conversations
user_id: default-user
```

The extraction model runs once per exchange, so a small fast model is the right choice
here. If it's unset, Suzent uses the default chat model.

## Consolidation

How often the dream runs, and how much it takes on. See
[How Consolidation Works](./consolidation.md).

```yaml
memory_consolidation_enabled: true
memory_consolidation_interval_seconds: 1800   # How often to check whether a run is due
memory_consolidation_min_hours: 24            # Minimum wait between runs
memory_consolidation_min_facts: 20            # New facts needed before a run is worth it
memory_consolidation_min_confirmations: 25    # Repeated facts that justify a run on their own
memory_consolidation_max_days: 14             # Days of logs read in one run
memory_consolidation_max_retries: 3           # Attempts before a stuck batch is skipped
memory_consolidation_timeout_seconds: 600
memory_consolidation_model: null              # Defaults to the main chat model
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

To use an existing Obsidian vault instead, mount it — this takes precedence over
`notebook_dir`, which stays pointing at the default path:

```yaml
sandbox_volumes:
  - "C:/Users/you/Documents/MyVault:/mnt/notebook"
```

## Search

```yaml
embedding_model: text-embedding-3-large
embedding_dimension: 3072        # 0 = detect from the model
embedding_timeout: 30            # Seconds before a slow provider is given up on
lancedb_uri: <data-dir>/memory
```

| Model | Dimensions | Cost / 1M tokens |
|---|---|---|
| `text-embedding-3-large` | 3072 | $0.13 |
| `text-embedding-3-small` | 1536 | $0.02 |

Changing the embedding model means re-embedding everything you've stored, which costs one
call per chunk across your whole memory. It is not a free switch.

## Sessions and transcripts

```yaml
SESSION_DAILY_RESET_HOUR: 0        # UTC hour for a daily reset (0 = off)
SESSION_IDLE_TIMEOUT_MINUTES: 0    # Reset after inactivity (0 = off)
JSONL_TRANSCRIPTS_ENABLED: true    # Keep a transcript per session
TRANSCRIPT_INDEXING_ENABLED: false # Also make transcripts searchable
```

Transcript indexing lets you search across past conversations, not just extracted facts.
It costs storage and embedding calls proportional to everything you say, which is why it
is off by default.

## Context window

```yaml
MAX_HISTORY_STEPS: 20              # Steps before a conversation is compressed
MAX_CONTEXT_TOKENS: 800000
```

## Rebuilding the search index

The Markdown files are the real memory; the search index is derived from them. If search
goes wrong, rebuild it — nothing is lost:

```bash
curl -X POST http://localhost:25314/memory/reindex -H "Content-Type: application/json" -d '{"clear_existing": true}'
```

A full rebuild re-embeds every file, so expect it to take a while and to cost embedding
calls.

## Debug logging

```bash
LOG_LEVEL=DEBUG uv run suzent
```
