# Memory System

A Letta-inspired dual-tier memory architecture enabling AI agents to maintain working memory and unlimited long-term storage with semantic recall.

## Overview

**Core Memory**: Always-visible working memory (4 blocks: persona, user, facts, context)
**Archival Memory**: Unlimited searchable storage with vector embeddings
**Automatic Management**: System extracts facts without explicit agent commands

Built on PostgreSQL + pgvector for production-ready persistence.

## Quick Example

```python
from suzent.memory import MemoryManager, PostgresMemoryStore

# Initialize
store = PostgresMemoryStore(connection_string)
await store.connect()

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-large",
    llm_for_extraction="gpt-4o-mini"
)

# Use
blocks = await manager.get_core_memory(user_id="user-123")
results = await manager.search_memories("user preferences", user_id="user-123")
```

## Key Features

- ✅ Core memory blocks (persona, user, facts, context)
- ✅ Semantic + full-text hybrid search
- ✅ Automatic LLM-based fact extraction
- ✅ **Rich Context Awareness** (captures extracted intent & outcomes)
- ✅ **Auto-summarizing Core Memory** (keeps "facts" block fresh)
- ✅ Importance scoring and deduplication
- ✅ Thread-safe agent tools

