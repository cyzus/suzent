# Memory System

A unified memory-session-agent architecture with human-readable markdown persistence, JSONL session transcripts, and inspectable agent state.

## Overview

**Markdown Memory** (`/shared/memory/`): Human-readable source of truth — daily logs and curated MEMORY.md, directly accessible by the agent via file tools.

**LanceDB Search Index** (`.suzent/memory/`): Vector + full-text hybrid search over extracted facts. Rebuilt from markdown if needed.

**Session Transcripts** (`.suzent/transcripts/`): Append-only JSONL logs per session for audit and cross-session search.

**Agent State** (`.suzent/state/`): Inspectable JSON snapshots replacing opaque pickle serialization.

**LLM Wiki** (`/mnt/notebook/`): A persistent, structured knowledge vault (Obsidian-style markdown) that the agent reads and writes directly. Distinct from conversation memory — this is a curated knowledge base rather than episodic logs. See [LLM Wiki](#llm-wiki) below.

## Quick Example

```python
from suzent.memory import MemoryManager, LanceDBMemoryStore
from suzent.memory.markdown_store import MarkdownMemoryStore

# Initialize stores
store = LanceDBMemoryStore(uri=".suzent/memory")
await store.connect()

markdown_store = MarkdownMemoryStore("/shared/memory")

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-large",
    llm_for_extraction="gpt-4o-mini",
    markdown_store=markdown_store,
)

# Use
blocks = await manager.get_core_memory(user_id="user-123")
results = await manager.search_memories("user preferences", user_id="user-123")
```

## Key Features

- Markdown as source of truth (daily logs + MEMORY.md)
- Dual-write: every fact persisted to both markdown and LanceDB
- Semantic + full-text hybrid search
- Automatic LLM-based fact extraction (concise one-sentence facts)
- Auto-summarizing core memory (refreshes MEMORY.md)
- Pre-compaction memory flush (captures facts before context compression)
- JSONL session transcripts with optional transcript indexing
- JSON v2 agent state (human-readable, backward-compatible with pickle)
- Session lifecycle management (daily reset, idle timeout, max turns)
- Importance scoring and deduplication
- Thread-safe agent tools
- Recovery: rebuild LanceDB from markdown via `MarkdownIndexer`
- LLM Wiki: agent-maintained knowledge vault bootstrapped by `WikiManager`

## LLM Wiki

> Pattern originally described by Andrej Karpathy: [LLM Wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)

The LLM Wiki is a structured knowledge base that lives alongside — but is separate from — the conversation memory system. It uses Obsidian-style markdown (wikilinks, callouts, frontmatter) and is organized according to a `schema.md` the agent reads before every operation.

**How it works:**
- The vault root is `/mnt/notebook` (sandbox) or `${MOUNT_NOTEBOOK}` (host).
- Three agent-maintained navigation files live at the vault root:
  - `schema.md` — vault conventions, folder layout, and page types. The agent reads this first on every operation.
  - `index.md` — catalog of synthesized pages, updated on every ingest or query filing.
  - `log.md` — append-only chronological record of all agent operations.
- The agent reads and writes vault pages directly via `ReadFileTool`/`WriteFileTool`/`EditFileTool`.
- `WikiManager` bootstraps these three files on first init (from `skills/notebook/schema_example.md`), then stays out of the way.

**Distinction from conversation memory:**

| | Conversation Memory | LLM Wiki |
|---|---|---|
| **Content** | Episodic facts extracted from chats | Synthesized knowledge pages |
| **Structure** | Daily logs + MEMORY.md + LanceDB | Obsidian vault (schema-defined folders) |
| **Written by** | `MemoryManager` (automatic extraction) | Agent directly via file tools |
| **Searched via** | LanceDB hybrid search | GlobTool + GrepTool + wikilinks |
| **Lifetime** | Accumulates across conversations | Persistent; updated by agent on ingest |

**Operational skills** (under `skills/notebook/`):
- `ingest.md` — procedure for ingesting new content into the vault
- `lint.md` — procedure for auditing and cleaning vault pages

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
