# Memory System - Technical Documentation

A Letta-inspired dual-tier memory architecture for Suzent that enables AI agents to maintain both working memory and unlimited long-term storage with semantic recall.

## Overview

This memory system provides AI agents with human-like memory capabilities:
- **Core Memory**: Always-visible working memory (like short-term memory)
- **Archival Memory**: Unlimited searchable storage (like long-term memory)
- **Automatic Management**: System extracts and indexes facts without explicit agent commands

The system is built on PostgreSQL with pgvector, providing ACID transactions, vector similarity search, and full-text search in a single database.

## Features Implemented

### Core Memory Blocks - Always-Visible Working Memory
- **Four structured blocks**: persona, user, facts, context
- **Update operations**: replace, append, search_replace
- **Automatic injection**: Core memory appears in every agent interaction
- **Scoping**: User-level persistence (persona/user/facts) and chat-level context

### Archival Memory - Unlimited Long-Term Storage
- **Vector embeddings**: Semantic search using text-embedding-3-large (3072 dimensions)
- **Hybrid search**: Combines semantic similarity + full-text + importance + recency
- **Access tracking**: Records retrieval frequency and timestamps
- **Importance scoring**: 0.0-1.0 scale for memory prioritization
- **Metadata support**: Tags, categories, and custom fields

### Automatic Fact Extraction
- **LLM-based extraction**: Uses structured prompts to extract facts from conversations
- **Category classification**: personal, preference, goal, context, technical
- **Importance scoring**: Automatic assessment of fact significance
- **Deduplication**: Prevents storing near-duplicate memories

### Agent Tools - Simple Interface
- `memory_search` - Semantic search across archival memories
- `memory_block_update` - Update core memory blocks with operations

### PostgreSQL + pgvector - Production-Ready Storage
- **ACID transactions**: Reliable data consistency
- **IVFFlat indexes**: Efficient vector similarity search for 3072-dim embeddings
- **Full-text search**: PostgreSQL tsvector for keyword matching
- **Relationship tracking**: Graph structure for memory connections (schema included)

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

## Component Architecture

### 1. PostgresMemoryStore (postgres_store.py)
**Database layer** - Direct interface to PostgreSQL + pgvector.

**Responsibilities:**
- Connection pool management with async support
- Core memory block CRUD operations
- Archival memory storage with vector embeddings
- Semantic search (pure vector similarity)
- Hybrid search (vector + full-text + importance + recency)
- Access tracking and statistics

**Key Methods:**
- `get_all_memory_blocks()` - Retrieve core memory with scoping priority
- `set_memory_block()` - Upsert core memory blocks
- `add_memory()` - Store new archival memory with embedding
- `semantic_search()` - Pure vector similarity search
- `hybrid_search()` - Combined scoring algorithm
- `get_memory_stats()` - Analytics and distribution

**Scoping Logic:**
Core memory blocks prioritize: chat-specific > user-level > global (NULL)

### 2. MemoryManager (manager.py)
**Orchestration layer** - Coordinates memory operations and automatic extraction.

**Responsibilities:**
- Core memory formatting for context injection
- Automatic fact extraction from conversations
- Deduplication of similar memories
- Embedding generation via LiteLLM
- Memory retrieval with relevance scoring

**Key Methods:**
- `get_core_memory()` - Returns all blocks with defaults
- `format_core_memory_for_context()` - Formats for prompt injection
- `retrieve_relevant_memories()` - Auto-retrieves context for queries
- `process_message_for_memories()` - Extracts and stores facts
- `search_memories()` - Agent-facing search interface
- `_extract_facts_llm()` - LLM-based structured extraction

**Fact Extraction Process:**
1. User message received
2. LLM extracts structured facts (content, category, importance, tags)
3. Semantic deduplication check (similarity > 0.85)
4. Store new facts in archival memory
5. Return extraction report

### 3. Memory Tools (tools.py)
**Agent interface** - Tools exposed to AI agents.

**MemorySearchTool:**
- Semantic search across archival memories
- Returns formatted results with relevance scores
- Thread-safe execution in main event loop
- Supports pagination with limit parameter

**MemoryBlockUpdateTool:**
- Update core memory blocks (persona, user, facts, context)
- Operations: replace, append, search_replace
- Automatic scoping (user-level vs chat-level)
- Validation and error handling

**Thread Safety:**
Both tools support running in the main event loop via `asyncio.run_coroutine_threadsafe()` for safe execution from agent worker threads.

### 4. Memory Context (memory_context.py)
**Prompt engineering** - Templates and formatting for agent instructions.

**Functions:**
- `format_core_memory_section()` - Creates memory context block for agent
- `format_retrieved_memories_section()` - Formats search results
- `format_fact_extraction_user_prompt()` - Templates for LLM extraction
- `FACT_EXTRACTION_SYSTEM_PROMPT` - Structured extraction instructions

## Data Flow

### Memory Injection Flow (Read Path)
```
User Query
    ↓
Agent Manager calls: manager.retrieve_relevant_memories(query)
    ↓
Generate query embedding → Hybrid search
    ↓
Format results with format_retrieved_memories_section()
    ↓
Inject into agent system prompt
    ↓
Agent processes with memory context
```

### Automatic Extraction Flow (Write Path)
```
User/Assistant Message
    ↓
Agent Manager calls: manager.process_message_for_memories()
    ↓
LLM extracts facts (if configured) → Returns [{content, category, importance, tags}]
    ↓
For each fact: Semantic deduplication check
    ↓
Store new facts with embeddings
    ↓
Return extraction report {created, updated, conflicts}
```

### Agent Tool Usage Flow
```
Agent decides to search memory
    ↓
Calls memory_search(query="user preferences")
    ↓
Tool executes in main loop → Returns formatted results
    ↓
Agent uses results in response
```

## File Structure

```
memory/
├── __init__.py           # Module exports
├── postgres_store.py     # Database layer - PostgreSQL + pgvector operations
├── manager.py            # Orchestration layer - Memory management logic
├── memory_context.py     # Prompt templates and formatting
├── tools.py              # Agent interface - Tools for memory operations
├── schema.sql            # Database schema definition
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

## Database Schema Details

### Core Tables

**memory_blocks** - Structured working memory
```sql
Columns:
- id (UUID): Primary key
- chat_id (TEXT): Optional chat context
- user_id (TEXT): Optional user context
- label (TEXT): Block type (persona, user, facts, context)
- content (TEXT): Block content
- max_size (INTEGER): Size limit (default 2048)
- created_at, updated_at (TIMESTAMPTZ): Timestamps

Indexes:
- Unique constraint on (label, chat_id, user_id)
- Indexes on chat_id, user_id, label for fast lookups
```

**archival_memories** - Long-term memory storage
```sql
Columns:
- id (UUID): Primary key
- chat_id (TEXT): Optional chat context
- user_id (TEXT): User identifier
- content (TEXT): Memory content
- embedding (vector(3072)): Vector embedding
- metadata (JSONB): Flexible metadata storage
- importance (REAL): 0.0-1.0 importance score
- created_at, updated_at, accessed_at (TIMESTAMPTZ)
- access_count (INTEGER): Retrieval frequency
- content_fts (tsvector): Full-text search index

Indexes:
- IVFFlat index on embedding for vector search
- GIN index on content_fts for full-text search
- GIN index on metadata for JSON queries
- B-tree indexes on user_id, importance, timestamps
```

**memory_relationships** - Memory graph (future use)
```sql
Columns:
- source_id, target_id (UUID): Memory references
- relationship_type (TEXT): related, conflicts_with, supersedes, etc.
- strength (REAL): Relationship strength 0.0-1.0

Purpose: Track semantic relationships between memories
```

### Hybrid Search Algorithm

The `hybrid_search()` method combines multiple signals:

```python
combined_score = (
    semantic_score * 0.7 +           # Vector similarity
    fts_score * 0.3 +                # Full-text match
    importance * 0.2 +               # User-defined importance
    recency_boost * 0.1              # Time-based decay
)
```

**Weights are configurable:**
- `semantic_weight`: Default 0.7
- `fts_weight`: Default 0.3
- `importance_boost`: Default 0.2
- `recency_boost`: Default 0.1

**Recency calculation:**
```python
recency = 1.0 / (1.0 + age_in_days)
```

This ensures recent memories get a slight boost while maintaining semantic relevance as primary signal.

## Configuration

### Environment Variables

```bash
# PostgreSQL Connection
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5430
POSTGRES_DB=suzent
POSTGRES_USER=suzent
POSTGRES_PASSWORD=password

# Embedding Model
EMBEDDING_MODEL=text-embedding-3-large  # or text-embedding-3-small
EMBEDDING_DIMENSION=3072                # Auto-detected if not set

# Fact Extraction LLM (optional)
MEMORY_EXTRACTION_MODEL=gpt-4o-mini    # If set, enables LLM extraction
```

### Memory Manager Initialization

```python
from suzent.memory import MemoryManager, PostgresMemoryStore

# Build connection string
connection_string = f"postgresql://{user}:{password}@{host}:{port}/{db}"

# Initialize store
store = PostgresMemoryStore(connection_string)
await store.connect()

# Initialize manager with LLM extraction
manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-large",
    embedding_dimension=3072,
    llm_for_extraction="gpt-4o-mini"  # Optional: enables LLM fact extraction
)
```

### Embedding Model Configuration

**Supported models** (via LiteLLM):
- `text-embedding-3-large` (3072 dim) - Recommended for production
- `text-embedding-3-small` (1536 dim) - Faster, lower cost
- `text-embedding-ada-002` (1536 dim) - Legacy OpenAI

**IMPORTANT:** Embedding dimension must match database schema:
```sql
-- Check current dimension
SELECT typname, typlen FROM pg_type WHERE typname = 'vector';

-- If mismatch, alter table
ALTER TABLE archival_memories ALTER COLUMN embedding TYPE vector(3072);
```

## API Reference

### MemoryManager

#### Core Memory Operations

```python
# Get all core memory blocks
blocks: Dict[str, str] = await manager.get_core_memory(
    chat_id="chat-123",  # Optional
    user_id="user-123"
)

# Update a specific block
success: bool = await manager.update_memory_block(
    label="facts",
    content="User prefers dark mode and uses VS Code",
    user_id="user-123"
)

# Format for agent context injection
context: str = await manager.format_core_memory_for_context(
    user_id="user-123"
)
```

#### Archival Memory Operations

```python
# Search memories (hybrid by default)
results: List[Dict] = await manager.search_memories(
    query="What are user's coding preferences?",
    limit=10,
    user_id="user-123",
    use_hybrid=True  # False for pure semantic
)

# Auto-retrieve relevant memories for a query
memory_context: str = await manager.retrieve_relevant_memories(
    query="Let's work on the Python project",
    user_id="user-123",
    limit=5
)

# Process message for automatic extraction
report: Dict = await manager.process_message_for_memories(
    message={"role": "user", "content": "I prefer tabs over spaces"},
    chat_id="chat-123",
    user_id="user-123"
)
# Returns: {extracted_facts, memories_created, memories_updated, conflicts_detected}
```

#### Statistics

```python
stats: Dict = await manager.get_memory_stats(user_id="user-123")
# Returns: {total_memories, user_id}
```

### PostgresMemoryStore

#### Memory CRUD

```python
# Add memory
memory_id: str = await store.add_memory(
    content="User is a Python developer",
    embedding=[0.1, 0.2, ...],  # 3072-dim vector
    user_id="user-123",
    metadata={"category": "technical", "tags": ["python"]},
    importance=0.8
)

# Update memory
success: bool = await store.update_memory(
    memory_id="uuid",
    content="Updated content",
    importance=0.9
)

# Delete memory
success: bool = await store.delete_memory(memory_id="uuid")

# Delete all for user
count: int = await store.delete_all_memories(user_id="user-123")
```

#### Search Operations

```python
# Pure semantic search
results: List[Dict] = await store.semantic_search(
    query_embedding=[0.1, 0.2, ...],
    user_id="user-123",
    limit=10,
    min_importance=0.5
)

# Hybrid search (recommended)
results: List[Dict] = await store.hybrid_search(
    query_embedding=[0.1, 0.2, ...],
    query_text="python preferences",
    user_id="user-123",
    limit=10,
    semantic_weight=0.7,
    fts_weight=0.3
)
```

#### Memory Listing and Stats

```python
# List memories with pagination
memories: List[Dict] = await store.list_memories(
    user_id="user-123",
    limit=20,
    offset=0,
    order_by='importance',  # or 'created_at', 'access_count'
    order_desc=True
)

# Get detailed statistics
stats: Dict = await store.get_memory_stats(user_id="user-123")
# Returns: {total_memories, avg_importance, importance_distribution, ...}
```

## Best Practices

### 1. Memory Scoping Strategy

**User-level memories** (persist across all chats):
- Persona information
- User preferences and facts
- Long-term goals

**Chat-level memories** (specific to conversation):
- Current context block
- Temporary session state

```python
# User-level (pass user_id, omit chat_id)
await manager.update_memory_block(
    label="facts",
    content="User is learning React",
    user_id="user-123"
    # chat_id=None  # User-level
)

# Chat-level (pass both)
await manager.update_memory_block(
    label="context",
    content="Currently debugging CORS issue",
    user_id="user-123",
    chat_id="chat-456"
)
```

### 2. Automatic vs Manual Memory Management

**Automatic extraction** (recommended):
```python
# Configure LLM extraction in MemoryManager
manager = MemoryManager(
    store=store,
    llm_for_extraction="gpt-4o-mini"
)

# Process each user message
await manager.process_message_for_memories(
    message=message,
    chat_id=chat_id,
    user_id=user_id
)
```

**Manual control** (for specific workflows):
```python
# Agent explicitly updates via tool
agent.tools = [MemorySearchTool(manager), MemoryBlockUpdateTool(manager)]
```

### 3. Search Strategy

**When to use hybrid search:**
- User queries with specific keywords
- Technical searches (e.g., "Python error handling")
- Combination of concepts

**When to use semantic search:**
- Conceptual queries
- Paraphrased questions
- Deduplication checks

### 4. Importance Scoring Guidelines

- **0.8-1.0**: Critical information (name, key preferences, major goals)
- **0.5-0.8**: Important context (tools used, recurring patterns)
- **0.0-0.5**: Minor details (one-time mentions, ephemeral info)

### 5. Performance Optimization

**Embedding caching:**
```python
# Cache embeddings for common queries
from functools import lru_cache

@lru_cache(maxsize=100)
def get_cached_embedding(query: str):
    return embedding_gen.generate(query)
```

**Connection pooling:**
```python
# Use appropriate pool size
store = PostgresMemoryStore(
    connection_string,
    min_size=2,    # Minimum connections
    max_size=10    # Maximum connections
)
```

**Index optimization:**
```sql
-- Periodically analyze tables
ANALYZE archival_memories;
ANALYZE memory_blocks;

-- Monitor index usage
SELECT * FROM pg_stat_user_indexes WHERE schemaname = 'public';
```

## Troubleshooting

### Vector Dimension Mismatch

**Error:** `ERROR: expected 1536 dimensions, not 3072`

**Solution:**
```sql
-- Check current dimension
\d+ archival_memories

-- Alter column
ALTER TABLE archival_memories
ALTER COLUMN embedding TYPE vector(3072);

-- Rebuild index
DROP INDEX idx_archival_memories_embedding;
CREATE INDEX idx_archival_memories_embedding ON archival_memories
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

### Slow Search Performance

**Symptoms:** Hybrid search taking >1 second

**Solutions:**
1. Ensure IVFFlat index is built
2. Increase `lists` parameter for larger datasets (100-1000)
3. Use `ANALYZE` to update statistics
4. Consider table partitioning for >1M memories

### Memory Extraction Not Working

**Check:**
1. Is `llm_for_extraction` set in MemoryManager?
2. Is API key configured?
3. Are you processing user messages (not assistant)?
4. Check logs for extraction failures

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Current Implementation Status

### Implemented
- Core memory blocks with CRUD operations
- Archival memory with vector embeddings
- Hybrid search algorithm
- LLM-based fact extraction
- Agent tools (search, update)
- Access tracking and statistics
- Thread-safe tool execution

### Not Yet Implemented
- **Conflict detection**: Detecting contradictory memories
- **Memory consolidation**: Merging related memories
- **Relationship graph**: Automatic relationship discovery
- **Background maintenance**: Importance decay, pruning
- **Frontend UI**: Memory visualization dashboard

## Integration Example

Here's a complete example of integrating the memory system with an AI agent:

```python
import asyncio
from suzent.memory import MemoryManager, PostgresMemoryStore
from suzent.memory import MemorySearchTool, MemoryBlockUpdateTool
from suzent.config import CONFIG

async def setup_memory_system():
    """Initialize memory system for agent."""

    # 1. Connect to PostgreSQL
    connection_string = (
        f"postgresql://{CONFIG.postgres_user}:{CONFIG.postgres_password}"
        f"@{CONFIG.postgres_host}:{CONFIG.postgres_port}/{CONFIG.postgres_db}"
    )

    store = PostgresMemoryStore(connection_string)
    await store.connect()

    # 2. Initialize memory manager with LLM extraction
    manager = MemoryManager(
        store=store,
        embedding_model="text-embedding-3-large",
        llm_for_extraction="gpt-4o-mini"
    )

    # 3. Create agent tools
    search_tool = MemorySearchTool(manager)
    update_tool = MemoryBlockUpdateTool(manager)

    # 4. Set context for current user/chat
    user_id = "user-123"
    chat_id = "chat-456"

    search_tool.set_context(chat_id=chat_id, user_id=user_id)
    update_tool.set_context(chat_id=chat_id, user_id=user_id)

    return manager, [search_tool, update_tool]

async def process_user_message(manager, user_message, chat_id, user_id):
    """Process a user message with memory system."""

    # 1. Retrieve relevant memories for context
    memory_context = await manager.retrieve_relevant_memories(
        query=user_message,
        user_id=user_id,
        limit=5
    )

    # 2. Get core memory for always-visible context
    core_memory = await manager.format_core_memory_for_context(
        chat_id=chat_id,
        user_id=user_id
    )

    # 3. Inject both into agent prompt
    enhanced_system_prompt = f"""
    {core_memory}

    {memory_context}

    [Rest of agent instructions...]
    """

    # 4. After agent responds, extract and store new facts
    await manager.process_message_for_memories(
        message={"role": "user", "content": user_message},
        chat_id=chat_id,
        user_id=user_id
    )

    return enhanced_system_prompt

# Usage
async def main():
    manager, tools = await setup_memory_system()

    # Process a message
    system_prompt = await process_user_message(
        manager,
        "I'm working on a React project with TypeScript",
        chat_id="chat-456",
        user_id="user-123"
    )

    print(system_prompt)

asyncio.run(main())
```

## Future Enhancements

### Phase 1: Enhanced Extraction (Next)
1. **Conflict detection**
   - Detect contradictory memories
   - User-guided or automatic resolution
   - Temporal reasoning (newer info supersedes older)

2. **Memory consolidation**
   - Merge duplicate/similar memories
   - Generate summaries of related facts
   - Topic clustering

### Phase 2: Advanced Features
3. **Relationship graph**
   - Automatic relationship discovery
   - Semantic connections between memories
   - Knowledge graph visualization

4. **Background maintenance**
   - Importance decay over time
   - Automatic pruning of low-value memories
   - Periodic consolidation jobs

### Phase 3: Frontend Integration
5. **Memory management UI**
   - View and edit memories
   - Memory timeline visualization
   - Search and filter interface
   - Manual memory curation

6. **Analytics dashboard**
   - Memory growth over time
   - Search pattern analysis
   - Importance distribution
   - Relationship graphs

### Phase 4: Optimization
7. **Performance improvements**
   - Embedding caching layer
   - Query result caching
   - Batch embedding generation
   - Optimized indexing strategies

8. **Testing and monitoring**
   - Comprehensive unit tests
   - Integration tests
   - Performance benchmarks
   - Memory usage monitoring

## System Constants

The following constants are defined in `manager.py` and can be tuned:

```python
# Memory retrieval limits
DEFAULT_MEMORY_RETRIEVAL_LIMIT = 5      # Auto-retrieval for queries
DEFAULT_MEMORY_SEARCH_LIMIT = 10        # Agent tool search default
IMPORTANT_MEMORY_THRESHOLD = 0.7        # High-importance cutoff

# Deduplication settings
DEDUPLICATION_SEARCH_LIMIT = 3          # How many similar memories to check
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.85  # Cosine similarity threshold

# Fact extraction
DEFAULT_IMPORTANCE = 0.5                # Default importance for extracted facts
LLM_EXTRACTION_TEMPERATURE = 1.0        # LLM creativity for extraction
```

### Tuning Recommendations

**For more aggressive memory storage:**
- Lower `DEDUPLICATION_SIMILARITY_THRESHOLD` to 0.75-0.80
- Increase `DEFAULT_IMPORTANCE` if facts are being undervalued

**For cleaner memory with less duplication:**
- Raise `DEDUPLICATION_SIMILARITY_THRESHOLD` to 0.90-0.95
- Increase `DEDUPLICATION_SEARCH_LIMIT` to 5-10

**For better context injection:**
- Increase `DEFAULT_MEMORY_RETRIEVAL_LIMIT` to 10-15
- Adjust hybrid search weights in PostgresMemoryStore

## References

- [Letta (MemGPT)](https://github.com/letta-ai/letta) - Original inspiration for dual-tier memory architecture
- [pgvector Documentation](https://github.com/pgvector/pgvector) - PostgreSQL vector extension
- [LiteLLM](https://github.com/BerriAI/litellm) - Unified LLM API for embeddings
- [smolagents](https://github.com/huggingface/smolagents) - Agent framework for tool integration

## License

Part of the Suzent project. See main repository for license details.
