# Architecture

## System Layers

```
┌─────────────────────────────────┐
│      Agent Tools                │  memory_search, memory_block_update
├─────────────────────────────────┤
│      MemoryManager              │  Orchestration & extraction
├─────────────────────────────────┤
│      PostgresMemoryStore        │  Database operations
├─────────────────────────────────┤
│      PostgreSQL + pgvector      │  Storage & indexing
└─────────────────────────────────┘
```

## Components

### PostgresMemoryStore (postgres_store.py)
**Database layer**

**Responsibilities:**
- Connection pool management
- Core memory block CRUD
- Archival memory with vector embeddings
- Semantic and hybrid search
- Statistics

**Key Methods:**
- `get_all_memory_blocks()` - Retrieve with scoping priority
- `add_memory()` - Store with embedding
- `semantic_search()` - Pure vector similarity
- `hybrid_search()` - Combined scoring

**Scoping:** chat-specific > user-level > global

### MemoryManager (manager.py)
**Orchestration layer**

**Responsibilities:**
- Core memory formatting
- Automatic fact extraction
- Deduplication
- Embedding generation

**Key Methods:**
- `get_core_memory()` - All blocks with defaults
- `format_core_memory_for_context()` - Prompt injection
- `retrieve_relevant_memories()` - Auto-retrieval
- `process_conversation_turn_for_memories()` - Extract from full context
- `refresh_core_memory_facts()` - Auto-summarize core memory
- `search_memories()` - Agent-facing search

**Extraction Process:**
1. Full Conversation Turn (User + Agent Steps + Response)
2. LLM extraction with "Rich Context" prompts
3. Deduplication check
4. Store unique facts
5. Monitor for high-importance facts -> Trigger Core Memory Refresh

### Memory Tools (tools.py)
**Agent interface**

**MemorySearchTool:**
- Semantic search across archival
- Formatted results with scores
- Thread-safe execution

**MemoryBlockUpdateTool:**
- Update core blocks
- Operations: replace, append, search_replace
- Auto-scoping (user vs chat level)

**Thread Safety:**
Uses `asyncio.run_coroutine_threadsafe()` for safe execution from worker threads.

### Memory Context (memory_context.py)
**Prompt templates**

- `format_core_memory_section()` - Agent context
- `format_retrieved_memories_section()` - Search results with intent/outcome
- `FACT_EXTRACTION_SYSTEM_PROMPT` - Rich extraction instructions
- `CORE_MEMORY_SUMMARIZATION_PROMPT` - Auto-summary instructions

## Data Flow

### Read Path (Memory Injection)
```
User Query
  ↓
manager.retrieve_relevant_memories()
  ↓
Generate embedding → Hybrid search
  ↓
Format results (Content + Context + Outcome)
  ↓
Inject into agent prompt
```

### Write Path (Extraction)
```
Conversation Turn (User + Agent + Response)
  ↓
manager.process_conversation_turn_for_memories()
  ↓
LLM extracts facts + context
  ↓
Store unique facts
  ↓
If High Importance -> refresh_core_memory_facts()
```

### Tool Usage
```
Agent decides to search
  ↓
Calls memory_search(query)
  ↓
Execute in main loop
  ↓
Return formatted results
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
├── __init__.py
├── postgres_store.py    # Database layer
├── manager.py           # Orchestration
├── memory_context.py    # Templates
├── tools.py             # Agent interface
└── schema.sql           # Schema
```

## Design Principles

1. **Separation of Concerns** - Clear layer boundaries
2. **Async by Default** - Non-blocking I/O
3. **Flexible Scoping** - Automatic priority resolution
4. **Automatic Management** - Facts extracted without commands
5. **Production Ready** - ACID, pooling, indexes

