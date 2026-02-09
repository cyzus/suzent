# Architecture

## System Layers

```
┌─────────────────────────────────┐
│      Agent Tools                │  memory_search, memory_block_update
├─────────────────────────────────┤
│      MemoryManager              │  Orchestration & extraction
├─────────────┬───────────────────┤
│  LanceDB    │  MarkdownStore    │  Dual-write storage
│  (search)   │  (source of truth)│
├─────────────┴───────────────────┤
│      Session Layer              │  Transcripts, state, lifecycle
└─────────────────────────────────┘
```

## Storage Tiers

### Markdown Files (`/shared/memory/`)
**Human-readable source of truth.** Agent-facing — the agent can read/write these files directly via `ReadFileTool`/`WriteFileTool`.

- **Daily logs** (`YYYY-MM-DD.md`): Append-only, timestamped facts per conversation turn
- **MEMORY.md**: Curated long-term summary, auto-updated by `refresh_core_memory_facts()`

### LanceDB (`.suzent/memory/`)
**Vector search index.** Rebuilt from markdown if corrupted via `MarkdownIndexer.reindex_from_markdown()`.

- Core memory blocks (persona, user, facts, context)
- Archival memories with vector embeddings
- Hybrid search: semantic + full-text + importance + recency

### Session Data (`.suzent/`)
**Internal operational data.** Not agent-facing — accessed via API endpoints.

- **Transcripts** (`.suzent/transcripts/{id}.jsonl`): Append-only per-session conversation logs
- **State snapshots** (`.suzent/state/{id}.json`): Inspectable JSON agent state mirrors

## Components

### MarkdownMemoryStore (markdown_store.py)
**Human-readable persistence layer**

- Manages files in `/shared/memory/` (cross-session, agent-accessible)
- Daily log format: lean single-line-per-fact (`- [category] content \`tag1 tag2\``)
- Methods: `append_daily_log()`, `get_recent_logs()`, `write_memory_file()`, `read_memory_file()`

### LanceDBMemoryStore (lancedb_store.py)
**Search index layer**

- LanceDB connection management
- Core memory block CRUD with scoping priority (chat > user > global)
- Archival memory with vector embeddings
- Semantic and hybrid search

### MemoryManager (manager.py)
**Orchestration layer**

- **Dual-write**: every extracted fact goes to both LanceDB and markdown
- Automatic LLM-based fact extraction (one concise sentence per fact)
- Deduplication via similarity threshold (0.85)
- Core memory refresh when high-importance facts are found
- Transcript linkage: facts track `source_session_id`, `source_transcript_line`, `source_timestamp`

### MarkdownIndexer (indexer.py)
**Recovery mechanism**

- `reindex_from_markdown()`: Rebuilds LanceDB from markdown daily logs
- Parses facts from markdown format, generates embeddings, stores in LanceDB

### TranscriptIndexer (indexer.py)
**Cross-session search**

- Chunks JSONL transcripts (~400 tokens, 80 overlap) into LanceDB
- Enables semantic search across past session conversations
- Opt-in via `transcript_indexing_enabled` config

### ContextCompressor (context_compressor.py)
**Context window management with pre-compaction flush**

- Before compressing steps, extracts facts from steps about to be removed
- Feeds synthetic `ConversationTurn` to `MemoryManager` for dual-write
- Ensures no valuable context is lost when the context window is trimmed

### Memory Tools (tools.py)
**Agent interface**

- `MemorySearchTool`: Semantic search across archival memory
- `MemoryBlockUpdateTool`: Update core blocks (replace, append, search_replace)
- Thread-safe via `asyncio.run_coroutine_threadsafe()`

### Memory Context (memory_context.py)
**Prompt templates**

- `FACT_EXTRACTION_SYSTEM_PROMPT`: One concise sentence per fact, no filler
- `CORE_MEMORY_SUMMARIZATION_PROMPT`: Max 200 words, bullet points only
- `format_core_memory_section()`: Includes Memory Workspace location (`/shared/memory/`)
- `format_retrieved_memories_section()`: Single-line format per memory

## Session Components

### TranscriptManager (session/transcript.py)
- Append-only JSONL files at `.suzent/transcripts/{session_id}.jsonl`
- Each line: `{"ts", "role", "content", "actions", "meta"}`
- Thread-safe with async locks per session

### StateMirror (session/state_mirror.py)
- Writes inspectable JSON snapshots to `.suzent/state/{session_id}.json`
- Parses JSON v2 agent state; writes placeholder for legacy pickle

### SessionLifecycle (session/lifecycle.py)
- `SessionPolicy`: daily reset hour, idle timeout, max turns
- `should_reset()`: checks all policies against session metadata

### Agent Serializer (core/agent_serializer.py)
- **JSON v2 format**: Human-readable, inspectable agent state
- Backward-compatible: auto-detects and loads legacy pickle format
- Serializes smolagents step objects (ActionStep, PlanningStep, TaskStep, FinalAnswerStep)

## Data Flow

### Write Path (Extraction + Dual-Write)
```
Conversation Turn (User + Agent + Response)
  ↓
manager.process_conversation_turn_for_memories()
  ↓
LLM extracts concise facts
  ↓
┌────────────────┬─────────────────────┐
│ LanceDB store  │ Markdown daily log  │
│ (search index) │ (source of truth)   │
└────────────────┴─────────────────────┘
  ↓
If High Importance → refresh_core_memory_facts() → MEMORY.md
```

### Read Path (Memory Injection)
```
User Query
  ↓
manager.retrieve_relevant_memories()
  ↓
Generate embedding → Hybrid search (LanceDB)
  ↓
Format results (single-line per memory)
  ↓
Inject into agent prompt
```

### Pre-Compaction Flush
```
Context compression triggered
  ↓
_pre_compaction_flush(steps_to_compress)
  ↓
Build synthetic ConversationTurn from steps
  ↓
Feed to memory extraction pipeline (dual-write)
  ↓
Compress steps into summary
```

### Session Lifecycle
```
New message arrives
  ↓
Write JSONL transcript entry
  ↓
Extract memories (dual-write)
  ↓
Check compression → pre-compaction flush if needed
  ↓
Persist state (JSON v2 + StateMirror)
  ↓
Update last_active_at, turn_count
```

## Memory Scoping

### User-Level
- **Scope:** All chats
- **Storage:** `user_id="x", chat_id=NULL`
- **Use:** Preferences, facts, persona

### Chat-Level
- **Scope:** Single conversation
- **Storage:** `user_id="x", chat_id="y"`
- **Use:** Current context, session state

### Global
- **Scope:** All users/chats
- **Storage:** `user_id=NULL, chat_id=NULL`
- **Use:** Default persona

### Priority
1. Chat-specific (most specific)
2. User-level (persistent)
3. Global (fallback)

## File Structure

```
src/suzent/memory/
├── __init__.py          # Exports
├── lancedb_store.py     # LanceDB search index
├── markdown_store.py    # Markdown source of truth (/shared/memory/)
├── indexer.py           # MarkdownIndexer + TranscriptIndexer
├── manager.py           # Orchestration & dual-write
├── memory_context.py    # Prompt templates
├── tools.py             # Agent tools
├── models.py            # Pydantic models
└── lifecycle.py         # Initialization

src/suzent/session/
├── __init__.py
├── transcript.py        # JSONL transcripts
├── state_mirror.py      # Agent state snapshots
└── lifecycle.py         # Session reset policies

src/suzent/core/
├── agent_serializer.py  # JSON v2 agent state
├── context_compressor.py # Pre-compaction flush
└── chat_processor.py    # Integration point

src/suzent/routes/
└── session_routes.py    # Transcript/state/memory APIs
```

## Data Layout

```
data/sandbox-data/
  shared/                           # Cross-session workspace (agent sees /shared/)
    memory/
      MEMORY.md                     # Curated long-term memory
      2026-02-08.md                 # Daily append-only logs

.suzent/
  chats.db                          # SQLite + session lifecycle fields
  memory/                           # LanceDB search index
  transcripts/
    {session_id}.jsonl              # Per-session conversation logs
  state/
    {session_id}.json               # Agent state snapshots
```

## Design Principles

1. **Markdown as Source of Truth** - Human-readable, git-friendly, recoverable
2. **Dual-Write** - Every fact persisted to both markdown and LanceDB
3. **No Context Loss** - Pre-compaction flush captures facts before compression
4. **Inspectable State** - JSON v2 replaces opaque pickle; state mirrors on disk
5. **Separation of Concerns** - Agent-facing (`/shared/`) vs internal (`.suzent/`)
6. **Async by Default** - Non-blocking I/O throughout
7. **Backward Compatible** - Legacy pickle deserialization, nullable migrations
