# Memory System# Memory System - Proof of Concept



Letta-style memory system for Suzent with dual-tier memory architecture.This is a proof-of-concept implementation of the Letta-style memory system for Suzent.



## Features## Features Implemented



✅ **Core Memory Blocks** - Always-visible working memory (persona, user, facts, context)  ✅ **Core Memory Blocks** - Always-visible working memory

✅ **Archival Memory** - Unlimited long-term storage with semantic search  - Persona, User, Facts, Context blocks

✅ **Automatic Fact Extraction** - Heuristic-based extraction (POC)  - Update operations (replace, append, search_replace)

✅ **Agent Tools** - `memory_search` and `memory_block_update`  

✅ **PostgreSQL + pgvector** - Single database with ACID transactions  ✅ **Archival Memory** - Unlimited long-term storage

- Vector embeddings for semantic search

## Quick Start- Hybrid search (semantic + full-text)

- Importance scoring and access tracking

### 1. Setup Database

✅ **Automatic Fact Extraction** - Simplified heuristic-based (POC)

```bash- Pattern matching for preferences, personal info, goals

# Using Docker (recommended)- Automatic storage of important facts

docker run -d \

  --name suzent-postgres \✅ **Agent Tools** - Only 2 tools exposed

  -e POSTGRES_USER=suzent \- `memory_search` - Recall memories semantically

  -e POSTGRES_PASSWORD=password \- `memory_block_update` - Update core memory blocks

  -e POSTGRES_DB=suzent \

  -p 5430:5432 \✅ **PostgreSQL + pgvector** - Single database solution

  pgvector/pgvector:pg18- ACID transactions

- Vector similarity search with HNSW index

# Run setup script- Full-text search with tsvector

./scripts/setup_memory_db.sh  # or .ps1 on Windows

```## Architecture



### 2. Configure Environment```

┌─────────────────────────────────────────┐

```bash│           Agent Tools                    │

# .env file│  • memory_search                         │

POSTGRES_HOST=127.0.0.1│  • memory_block_update                   │

POSTGRES_PORT=5430└─────────────────┬───────────────────────┘

POSTGRES_DB=suzent                  │

POSTGRES_USER=suzent┌─────────────────▼───────────────────────┐

POSTGRES_PASSWORD=password│         MemoryManager                    │

│  • Core memory formatting                │

# Embedding model API key│  • Archival search                       │

OPENAI_API_KEY=sk-xxx  # or other provider│  • Automatic extraction                  │

```└─────────────────┬───────────────────────┘

                  │

### 3. Install Dependencies┌─────────────────▼───────────────────────┐

│      PostgresMemoryStore                 │

```bash│  • Vector operations (pgvector)          │

uv sync --all-extras│  • Hybrid search                         │

```│  • Memory CRUD                           │

└─────────────────┬───────────────────────┘

### 4. Run Demo                  │

┌─────────────────▼───────────────────────┐

```bash│      PostgreSQL + pgvector               │

python -m suzent.memory.demo│  • memory_blocks table                   │

```│  • archival_memories table               │

│  • Vector indexes (HNSW)                 │

## Architecture└──────────────────────────────────────────┘

```

```

Agent Tools (memory_search, memory_block_update)## Setup

              ↓

      MemoryManager### 1. Install PostgreSQL with pgvector

              ↓

   PostgresMemoryStore```bash

              ↓# Ubuntu/Debian

PostgreSQL + pgvectorsudo apt install postgresql postgresql-contrib

```sudo apt install postgresql-14-pgvector



## Usage# macOS

brew install postgresql pgvector

```python

from suzent.memory import MemoryManager, PostgresMemoryStore# Or use Docker

docker run -d \

# Initialize  --name suzent-postgres \

store = PostgresMemoryStore(connection_string)  -e POSTGRES_USER=suzent \

await store.connect()  -e POSTGRES_PASSWORD=password \

manager = MemoryManager(store=store)  -e POSTGRES_DB=suzent \

  -p 5432:5432 \

# Get core memory  ankane/pgvector

blocks = await manager.get_core_memory(user_id="user-123")```



# Search archival memory### 2. Initialize Database Schema

results = await manager.search_memories(

    query="What are user's preferences?",```bash

    user_id="user-123",# Connect to PostgreSQL

    limit=5psql -U suzent -d suzent

)

# Run the schema file

# Update core memory\i src/suzent/memory/schema.sql

await manager.update_memory_block(```

    label="facts",

    content="User prefers dark mode",Or from command line:

    user_id="user-123"

)```bash

```psql -U suzent -d suzent -f src/suzent/memory/schema.sql

```

## File Structure

### 3. Install Python Dependencies

```

memory/```bash

├── __init__.py           # Module exportsuv sync --extra memory

├── postgres_store.py     # PostgreSQL + pgvector operations```

├── manager.py            # Memory orchestration

├── embeddings.py         # Embedding generation (LiteLLM)### 4. Set Environment Variables

├── tools.py              # Agent tools

├── schema.sql            # Database schema```bash

├── demo.py               # Demo scriptexport 

└── README.md             # This fileexport OPENAI_API_KEY="your-key-here"  # For embeddings

``````



## Documentation## Usage



- **[Quick Start Guide](../../../docs/MEMORY_QUICKSTART.md)** - Step-by-step setup### Run the Demo

- **[Design Document](../../../docs/MEMORY_SYSTEM_DESIGN.md)** - Full architecture

- **[Letta (MemGPT)](https://github.com/letta-ai/letta)** - Inspiration```bash

# From project root

## Limitations (POC)python -m suzent.memory.demo

```

This is a proof-of-concept with simplified implementations:

### Integrate with Agent

- **Fact extraction**: Simple heuristics (needs LLM-based extraction)

- **Conflict detection**: Not implemented```python

- **Memory consolidation**: Not implementedfrom suzent.memory import MemoryManager, PostgresMemoryStore

- **Relationship graphs**: Not implementedfrom suzent.memory import MemorySearchTool, MemoryBlockUpdateTool



See the design document for production requirements.# 1. Initialize

store = PostgresMemoryStore(connection_string)
await store.connect()

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-small"
)

# 2. Create tools for agent
search_tool = MemorySearchTool(manager)
update_tool = MemoryBlockUpdateTool(manager)

# Inject context
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
├── embeddings.py         # Embedding generation
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

- [Design Document](../../../docs/MEMORY_SYSTEM_DESIGN.md)
- [Letta (MemGPT)](https://github.com/letta-ai/letta)
- [pgvector Documentation](https://github.com/pgvector/pgvector)
