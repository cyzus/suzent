# Configuration

## Environment Variables

### LanceDB Storage
```bash
# Path to LanceDB storage (default: .suzent/data/memory)
# Can be relative or absolute path
LANCEDB_URI=.suzent/data/memory
```

### Embedding
```bash
EMBEDDING_MODEL=text-embedding-3-large  # or text-embedding-3-small
EMBEDDING_DIMENSION=3072                # Auto-detected from CONFIG if omitted
```

### Memory System
```bash
MEMORY_ENABLED=true                    # Enable/disable memory system
EXTRACTION_MODEL=gpt-4o-mini          # LLM for fact extraction (optional)
USER_ID=default-user                   # Default user identifier
```

### API Keys
```bash
OPENAI_API_KEY=sk-xxx
```

## Manager Initialization

```python
from suzent.memory import MemoryManager, LanceDBMemoryStore

# Initialize store
store = LanceDBMemoryStore(
    uri=".suzent/data/memory",
    embedding_dim=3072
)
await store.connect()

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-large",
    embedding_dimension=3072,  # Optional
    llm_for_extraction="gpt-4o-mini"  # Optional
)
```

## System Constants

Defined in `manager.py`:

```python
DEFAULT_MEMORY_RETRIEVAL_LIMIT = 5
DEFAULT_MEMORY_SEARCH_LIMIT = 10
IMPORTANT_MEMORY_THRESHOLD = 0.7
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.85
DEFAULT_IMPORTANCE = 0.5
```

## Tuning

### More Aggressive Storage
```python
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.75
DEFAULT_IMPORTANCE = 0.6
```

### Cleaner Memory
```python
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.90
DEFAULT_IMPORTANCE = 0.3
```

### Hybrid Search Weights
```python
results = await store.hybrid_search(
    ...,
    semantic_weight=0.7,      # Vector similarity
    fts_weight=0.3,           # Full-text
    importance_boost=0.2,     # Importance
    recency_boost=0.1         # Recency
)
```

## Embedding Models

| Model | Dimension | Cost/1M tokens | Use Case |
|-------|-----------|----------------|----------|
| text-embedding-3-large | 3072 | $0.13 | Production |
| text-embedding-3-small | 1536 | $0.02 | Development |
| text-embedding-ada-002 | 1536 | $0.10 | Legacy |

## Storage Management

### Check Storage Size
```python
import os
from pathlib import Path

db_path = Path(".suzent/data/memory")
if db_path.exists():
    total_size = sum(f.stat().st_size for f in db_path.rglob('*') if f.is_file())
    print(f"Memory storage: {total_size / (1024**2):.2f} MB")
```

### Clear All Memories
```python
# Delete all memories for a user
await store.delete_all_memories(user_id="user-123")
```

## Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

