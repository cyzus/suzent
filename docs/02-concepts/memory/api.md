# API Reference

Complete API documentation for the unified memory-session system.

## MemoryManager

### Initialization

```python
MemoryManager(
    store: LanceDBMemoryStore,
    embedding_model: str = None,
    embedding_dimension: int = 0,
    llm_for_extraction: Optional[str] = None,
    markdown_store: Optional[MarkdownMemoryStore] = None
)
```

### Core Memory

#### get_core_memory()
```python
await manager.get_core_memory(
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, str]
```

Returns: `{'persona': '...', 'user': '...', 'facts': '...', 'context': '...'}`

#### update_memory_block()
```python
await manager.update_memory_block(
    label: str,  # 'persona', 'user', 'facts', 'context'
    content: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> bool
```

#### format_core_memory_for_context()
```python
await manager.format_core_memory_for_context(
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> str
```

Returns formatted string for system prompt, including Memory Workspace location.

### Archival Memory

#### search_memories()
```python
await manager.search_memories(
    query: str,
    limit: int = 10,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    use_hybrid: bool = True
) -> List[Dict[str, Any]]
```

Returns list of memory dicts with `id`, `content`, `importance`, `similarity`, `created_at`, `metadata`.

#### retrieve_relevant_memories()
```python
await manager.retrieve_relevant_memories(
    query: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None,
    limit: int = 5
) -> str
```

Returns formatted string with relevant memories or empty string.

#### process_conversation_turn_for_memories()
```python
await manager.process_conversation_turn_for_memories(
    conversation_turn: Union[ConversationTurn, Dict],
    chat_id: str,
    user_id: str
) -> MemoryExtractionResult
```

Dual-writes extracted facts to LanceDB and markdown daily log.

Returns: `MemoryExtractionResult` with `extracted_facts`, `memories_created`, `memories_updated`.

#### refresh_core_memory_facts()
```python
await manager.refresh_core_memory_facts(user_id: str)
```

Summarizes high-importance facts into the `facts` core block and writes to `MEMORY.md`.

#### get_memory_stats()
```python
await manager.get_memory_stats(user_id: str) -> Dict[str, Any]
```

Returns: `{'total_memories': int, 'user_id': str}`

## MarkdownMemoryStore

### Initialization

```python
MarkdownMemoryStore(base_dir: str)
# e.g. MarkdownMemoryStore("/shared/memory")
```

### Daily Logs

#### append_daily_log()
```python
await store.append_daily_log(
    chat_id: str,
    facts: List[dict],  # [{"content", "category", "tags", ...}]
    date: Optional[str] = None  # YYYY-MM-DD, defaults to today
)
```

#### get_recent_logs()
```python
await store.get_recent_logs(days: int = 2) -> str
```

#### list_daily_logs()
```python
await store.list_daily_logs() -> List[str]  # ["2026-02-08", ...]
```

### Long-term Memory

#### write_memory_file()
```python
await store.write_memory_file(content: str)
```

Writes/replaces `MEMORY.md` with header and timestamp.

#### read_memory_file()
```python
await store.read_memory_file() -> Optional[str]
```

## MarkdownIndexer

### reindex_from_markdown()
```python
indexer = MarkdownIndexer()
stats = await indexer.reindex_from_markdown(
    markdown_store,
    lancedb_store,
    embedding_gen,
    user_id: str,
    clear_existing: bool = False
) -> dict  # {total_files, total_facts, indexed, skipped, errors}
```

Rebuilds LanceDB from markdown source of truth.

## TranscriptIndexer

### index_transcript()
```python
indexer = TranscriptIndexer(chunk_size=400, chunk_overlap=80)
stats = await indexer.index_transcript(
    transcript_path: Path,
    session_id: str,
    lancedb_store,
    embedding_gen,
    user_id: str
) -> dict  # {total_turns, total_chunks, indexed, errors}
```

Chunks JSONL transcript and embeds into LanceDB for cross-session search.

## TranscriptManager

### Initialization

```python
TranscriptManager(base_dir: Optional[str] = None)
# Defaults to .suzent/transcripts/
```

### Methods

#### append_turn()
```python
await mgr.append_turn(
    session_id: str,
    role: str,      # "user" or "assistant"
    content: str,
    actions: Optional[List[dict]] = None,
    metadata: Optional[dict] = None
)
```

#### read_transcript()
```python
await mgr.read_transcript(
    session_id: str,
    last_n: Optional[int] = None
) -> List[dict]
```

#### transcript_exists()
```python
mgr.transcript_exists(session_id: str) -> bool
```

## StateMirror

### Initialization

```python
StateMirror(base_dir: Optional[str] = None)
# Defaults to .suzent/state/
```

### Methods

#### mirror_state()
```python
mirror.mirror_state(session_id: str, state_bytes: bytes)
```

Writes human-readable JSON from serialized agent state. Falls back to placeholder for pickle format.

#### read_state()
```python
mirror.read_state(session_id: str) -> Optional[dict]
```

## SessionLifecycle

### Initialization

```python
policy = SessionPolicy(
    daily_reset_hour: int = 4,     # UTC hour (0 = disabled)
    idle_timeout_minutes: int = 0, # 0 = disabled
    max_turns: int = 0             # 0 = unlimited
)
lifecycle = SessionLifecycle(policy)
```

### Methods

#### should_reset()
```python
lifecycle.should_reset(
    last_active_at: datetime,
    turn_count: int = 0,
    created_at: Optional[datetime] = None
) -> Tuple[bool, str]  # (should_reset, reason)
```

#### get_session_key()
```python
SessionLifecycle.get_session_key(
    platform: str,
    sender_id: str,
    thread_id: Optional[str] = None
) -> str  # e.g. "telegram-user123-thread456"
```

## ContextCompressor

### Initialization

```python
ContextCompressor(
    llm_client: Optional[LLMClient] = None,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
)
```

### Methods

#### compress_context()
```python
await compressor.compress_context(agent: CodeAgent) -> bool
```

Runs pre-compaction memory flush before compressing, then summarizes old steps.

## Agent Tools

### MemorySearchTool

```python
MemorySearchTool(memory_manager: MemoryManager)
tool.set_context(chat_id, user_id)
result = tool.forward(query: str, limit: int = 10) -> str
```

### MemoryBlockUpdateTool

```python
MemoryBlockUpdateTool(memory_manager: MemoryManager)
tool.set_context(chat_id, user_id)
result = tool.forward(
    block: str,           # 'persona', 'user', 'facts', 'context'
    operation: str,       # 'replace', 'append', 'search_replace'
    content: str,
    search_pattern: Optional[str] = None
) -> str
```

## LanceDBMemoryStore

### Initialization

```python
LanceDBMemoryStore(
    uri: str = ".suzent/data/memory",
    embedding_dim: int = CONFIG.embedding_dimension
)
await store.connect()
```

### Memory Blocks

#### get_all_memory_blocks()
```python
await store.get_all_memory_blocks(
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Dict[str, str]
```

#### set_memory_block()
```python
await store.set_memory_block(
    label: str,
    content: str,
    chat_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> bool
```

### Archival Memory

#### add_memory()
```python
await store.add_memory(
    content: str,
    embedding: List[float],
    user_id: str,
    chat_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    importance: float = 0.5
) -> str  # Returns memory ID
```

### Search

#### hybrid_search()
```python
await store.hybrid_search(
    query_embedding: List[float],
    query_text: str,
    user_id: str,
    limit: int = 10,
    chat_id: Optional[str] = None,
    semantic_weight: float = 0.7,
    fts_weight: float = 0.3,
    recency_boost: float = 0.1,
    importance_boost: float = 0.2
) -> List[Dict[str, Any]]
```

## REST API Endpoints

### Session Inspection

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/session/{id}/transcript` | GET | Session transcript (`?last_n=N`) |
| `/session/{id}/state` | GET | Agent state snapshot |

### Memory Files

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/memory/daily` | GET | List daily log dates |
| `/memory/daily/{date}` | GET | Daily log content |
| `/memory/file` | GET | MEMORY.md content |
| `/memory/reindex` | POST | Rebuild LanceDB from markdown |

### Core Memory

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/memory/core` | GET | Get core memory blocks |
| `/memory/core` | PUT | Update a core memory block |
| `/memory/archival` | GET | Search archival memories |
| `/memory/archival/{id}` | DELETE | Delete a memory |
| `/memory/stats` | GET | Memory statistics |

## Type Definitions

### ExtractedFact
```python
{
    'content': str,
    'category': str,       # personal, preference, goal, context, technical
    'importance': float,   # 0.0-1.0
    'tags': List[str],
    # Transcript linkage
    'source_session_id': Optional[str],
    'source_transcript_line': Optional[int],
    'source_timestamp': Optional[str],
}
```

### Transcript Entry (JSONL line)
```json
{"ts": "2026-02-08T14:32:00Z", "role": "user", "content": "...", "actions": [...], "meta": {...}}
```

### Agent State (JSON v2)
```json
{"version": 2, "steps": [...], "tools": [...], "serialized_at": "..."}
```
