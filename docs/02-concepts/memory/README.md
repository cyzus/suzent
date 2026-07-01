# Memory System

Suzent remembers things across conversations — facts you've shared, preferences, and context from past sessions. Memory is stored as human-readable markdown files you can inspect and edit directly.

## What gets remembered

**Conversation memory** (`/shared/memory/`): Facts extracted automatically from each chat — stored as daily logs and a curated `MEMORY.md` summary. The agent can read and search these files directly.

**LLM Wiki** (`/mnt/notebook/`): A structured knowledge vault the agent builds and maintains over time. Separate from conversation memory — used for synthesized knowledge rather than episodic facts. See [LLM Wiki](./llm-wiki.md).

## Storage layout

```
/shared/memory/          # Agent-accessible (cross-session)
  MEMORY.md              # Curated long-term summary
  2026-02-08.md          # Daily append-only logs

.suzent/
  memory/                # LanceDB search index (rebuilt from markdown if needed)
  transcripts/           # Per-session conversation logs
  state/                 # Agent state snapshots
```

## Deep dives

- [Memory Consolidation](./consolidation.md): How daily logs become consolidated notebook memory.
- [Memory Internals](./internals.md): Implementation-level architecture and data flow.

## Configuration

Key settings in `config/default.yaml`:

```yaml
MEMORY_ENABLED: true
MARKDOWN_MEMORY_ENABLED: true      # Write facts to /shared/memory/ markdown files
EXTRACTION_MODEL: gpt-4o-mini      # LLM used to extract facts from conversations
EMBEDDING_MODEL: text-embedding-3-large

# Session lifecycle
SESSION_DAILY_RESET_HOUR: 0        # UTC hour for daily reset (0 = disabled)
SESSION_IDLE_TIMEOUT_MINUTES: 0    # 0 = disabled

# Context window
MAX_HISTORY_STEPS: 20              # Steps before compression triggers
MAX_CONTEXT_TOKENS: 800000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/memory/core` | GET | Get core memory blocks |
| `/memory/core` | PUT | Update a core memory block |
| `/memory/archival` | GET | Search archival memories |
| `/memory/archival/{id}` | DELETE | Delete a memory |
| `/memory/stats` | GET | Memory statistics |
| `/memory/daily` | GET | List daily log dates |
| `/memory/daily/{date}` | GET | Get daily log content |
| `/memory/file` | GET | Get MEMORY.md content |
| `/memory/reindex` | POST | Rebuild LanceDB from markdown |
| `/session/{id}/transcript` | GET | Get session transcript |
| `/session/{id}/state` | GET | Get agent state snapshot |
