# Memory Configuration

Most people never open this page. Memory is on out of the box, and the two settings you
are most likely to want — whether it runs at all, and which models it uses — are in
**Settings → Memory** in the app.

What follows is the tuning that has no UI. Put overrides in `~/.suzent/config/default.yaml`
(machine-specific paths belong in `~/.suzent/config/local.yaml`); both are read after the
shipped `config/default.example.yaml`, so anything you set there wins and survives an
update. Keys are case-insensitive — `MEMORY_ENABLED` and `memory_enabled` are the same
setting.

## The basics

```yaml
memory_enabled: true               # Also the toggle in Settings → Memory
markdown_memory_enabled: true      # Write facts to /shared/memory/ as Markdown
extraction_model: gemini/gemini-2.5-flash   # "" for heuristic extraction, no model call
user_id: default-user
```

The extraction model runs once per exchange, so a small fast model is the right choice
here. Leave it unset to use the default chat model.

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

Pick the embedding model in **Settings → Memory** — the list is filtered to what your
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

The compaction budget is derived from the model actually running the conversation:
its input window, read from the model capability registry. A 1M-token model gets a
1M-token budget, a 128k model gets 128k, and compaction triggers at the same
*fraction* of each (`context_compaction_trigger`, 80% by default) instead of at one
fixed token count that was wrong for every model but one.

Set `max_context_tokens` to a non-zero value to cap that budget — useful to keep
prompts (and cost) below what the model would allow. It is a ceiling, never a
raise: the smaller of the two always wins. When a model is missing from the
registry, the budget falls back to 200k tokens.

## Rebuilding the search index

The Markdown files are the real memory; the search index is derived from them. If search
goes wrong, rebuild it — nothing is lost:

```bash
curl -X POST http://localhost:25314/memory/reindex -H "Content-Type: application/json" -d '{"clear_existing": true}'
```

A full rebuild re-embeds every file, so expect it to take a while and to cost embedding
calls.

## The memory API

Everything the Memory panel does is available over HTTP, on the same port as the app
(`25314` unless you set `SUZENT_PORT`), so you can script it or wire it into your own tools.

| Endpoint | Method | What it does |
|---|---|---|
| `/memory/core` | GET | Read the core blocks (`persona`, `user`, `facts`, `context`) |
| `/memory/core` | PUT | Overwrite one core block |
| `/memory/file` | GET | Read `MEMORY.md` |
| `/memory/daily` | GET | List the dates that have a daily log |
| `/memory/daily/{date}` | GET | Read one day's log |
| `/memory/archival` | GET | Search remembered facts |
| `/memory/archival/{id}` | DELETE | Forget one fact (records a tombstone) |
| `/memory/stats` | GET | Counts and index size |
| `/memory/project-contexts` | GET | List per-project context files |
| `/memory/project-contexts/{id}` | PUT | Update a project's context |
| `/memory/reindex` | POST | Rebuild the search index from Markdown |
| `/memory/dream/status` | GET | Consolidation progress and pending work |
| `/memory/consolidate` | POST | Run consolidation now |
| `/memory/lint` | POST | Run the notebook audit now |

Editing a core block through `PUT /memory/core` counts as *you* saying it, which outranks
anything the agent worked out on its own — see
[MEMORY.md is half yours](https://suzent.com/docs/concepts/memory#memorymd-is-half-yours).

## Debug logging

```bash
LOG_LEVEL=DEBUG uv run suzent
```
