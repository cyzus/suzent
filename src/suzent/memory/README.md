# Memory System - Proof of Concept

Letta-style memory system for Suzent with dual-tier memory architecture.

## Features Implemented

**Core Memory Blocks** - Always-visible working memory
- Persona, User, Facts, Context blocks
- Update operations (replace, append, search_replace)
- Automatically injected into agent context

**Archival Memory** - Unlimited long-term storage
- Vector embeddings for semantic search
- Hybrid search (semantic + full-text)
- Importance scoring and access tracking

**Automatic Fact Extraction** - Simplified heuristic-based (POC)
- Pattern matching for preferences, personal info, goals
- Automatic storage of important facts

**Agent Tools** - Only 2 tools exposed
- `memory_search` - Recall memories semantically
- `memory_block_update` - Update core memory blocks

**PostgreSQL + pgvector** - Single database solution
- ACID transactions
- Vector similarity search with HNSW index
- Full-text search with tsvector

## Architecture

```
┌─────────────────────────────────────────┐
│           Agent Tools                    │
│  • memory_search                         │
│  • memory_block_update                   │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         MemoryManager                    │
│  • Core memory formatting                │
│  • Archival search                       │
│  • Automatic extraction                  │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      PostgresMemoryStore                 │
│  • Vector operations (pgvector)          │
│  • Hybrid search                         │
│  • Memory CRUD                           │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│      PostgreSQL + pgvector               │
│  • memory_blocks table                   │
│  • archival_memories table               │
│  • Vector indexes (HNSW)                 │
└──────────────────────────────────────────┘
```

## Quick Start

### 1. Setup Database

Using Docker (recommended):

```bash
docker run -d \
  --name suzent-postgres \
  -e POSTGRES_USER=suzent \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=suzent \
  -p 5430:5432 \
  pgvector/pgvector:pg18
```

Run setup script:

```bash
# Linux/macOS
./scripts/setup_memory_db.sh

# Windows
.\scripts\setup_memory_db.ps1
```

### 2. Configure Environment

Add to your `.env` file:

```bash
# PostgreSQL Configuration
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5430
POSTGRES_DB=suzent
POSTGRES_USER=suzent
POSTGRES_PASSWORD=password

# Embedding Model API Key
OPENAI_API_KEY=sk-xxx  # or other provider
```

### 3. Install Dependencies

```bash
uv sync
```


## Usage

### Basic Operations

```python
from suzent.memory import MemoryManager, PostgresMemoryStore

# 1. Initialize
store = PostgresMemoryStore(connection_string)
await store.connect()

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-small"
)

# 2. Get core memory
blocks = await manager.get_core_memory(user_id="user-123")

# 3. Search archival memory
results = await manager.search_memories(
    query="What are user's preferences?",
    user_id="user-123",
    limit=5
)

# 4. Update core memory
await manager.update_memory_block(
    label="facts",
    content="User prefers dark mode",
    user_id="user-123"
)
```

### Integrate with Agent

```python
from suzent.memory import MemorySearchTool, MemoryBlockUpdateTool

# 1. Create tools for agent
search_tool = MemorySearchTool(manager)
update_tool = MemoryBlockUpdateTool(manager)

# 2. Inject context
search_tool._user_id = "user-123"
update_tool._user_id = "user-123"

# 3. Add tools to agent
agent = CodeAgent(
    tools=[search_tool, update_tool, ...],
    ...
)

# 4. Inject core memory into custom instructions
custom_instructions = await manager.format_core_memory_for_context(
    user_id="user-123"
)

# 5. Process messages for automatic extraction
await manager.process_message_for_memories(
    message={"role": "user", "content": "..."},
    chat_id="chat-123",
    user_id="user-123"
)
```

## File Structure

```
memory/
├── __init__.py           # Module exports
├── postgres_store.py     # PostgreSQL + pgvector operations
├── manager.py            # Memory orchestration
├── tools.py              # Agent-facing tools
├── schema.sql            # Database schema
├── demo.py               # Proof-of-concept demo
└── README.md             # This file
```

## Key Concepts

### Core Memory (In-Context)
- **Always visible** to the agent in every interaction
- Limited size (~2KB per block)
- 4 blocks: persona, user, facts, context
- Agent can explicitly update using `memory_block_update` tool

### Archival Memory (Out-of-Context)
- **Unlimited storage**, semantically searchable
- Automatically extracted from conversations
- Retrieved when needed via `memory_search` tool
- Importance-based ranking and pruning

### Automatic Management
- Agents **don't manually add/delete memories**
- System extracts facts automatically
- Handles deduplication and conflicts
- Manages importance decay and pruning

## Limitations (POC)

This is a proof-of-concept with simplified implementations:

- **Fact extraction**: Uses simple heuristics instead of LLM
- **Conflict detection**: Not implemented
- **Memory consolidation**: Not implemented
- **Relationship graph**: Not implemented
- **Background maintenance**: Not implemented

For production, these would need full implementation as described in the design document.

## Next Steps

To move from POC to production:

1. **LLM-based fact extraction**
   - Replace heuristics with LLM prompting
   - Extract structured facts with categories and importance

2. **Conflict detection and resolution**
   - Detect contradictory information
   - Automatic or user-guided resolution

3. **Memory consolidation**
   - Merge related memories
   - Create higher-level summaries

4. **Background maintenance tasks**
   - Importance decay over time
   - Automatic pruning of low-value memories
   - Relationship discovery

5. **Frontend integration**
   - Memory visualization UI
   - Manual memory management interface
   - Memory analytics dashboard

6. **Testing and optimization**
   - Unit tests for all components
   - Performance benchmarks
   - Embedding caching
   - Query optimization

## References
- [Letta (MemGPT)](https://github.com/letta-ai/letta)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
