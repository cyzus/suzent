# Configuration

## YAML Configuration

All memory and session settings go in `config/default.yaml`:

```yaml
# Memory system
MEMORY_ENABLED: true
MARKDOWN_MEMORY_ENABLED: true      # Dual-write to /shared/memory/ markdown files
EXTRACTION_MODEL: gpt-4o-mini      # LLM for fact extraction
USER_ID: default-user

# Embedding
EMBEDDING_MODEL: text-embedding-3-large
EMBEDDING_DIMENSION: 3072           # 0 = auto-detect

# Session lifecycle
SESSION_DAILY_RESET_HOUR: 0         # UTC hour for daily reset (0 = disabled)
SESSION_IDLE_TIMEOUT_MINUTES: 0     # 0 = disabled
JSONL_TRANSCRIPTS_ENABLED: true     # Write per-session JSONL transcripts
TRANSCRIPT_INDEXING_ENABLED: false   # Index transcripts into LanceDB for search

# Context management
MAX_HISTORY_STEPS: 20               # Steps before compression triggers
MAX_CONTEXT_TOKENS: 800000          # Token threshold for compression
```

## Environment Variables

### API Keys
```bash
OPENAI_API_KEY=sk-xxx
```

### LanceDB Storage
```bash
# Path to LanceDB storage (default: .suzent/memory)
LANCEDB_URI=.suzent/memory
```

## Manager Initialization

```python
from suzent.memory import MemoryManager, LanceDBMemoryStore
from suzent.memory.markdown_store import MarkdownMemoryStore

# Initialize stores
store = LanceDBMemoryStore(uri=".suzent/memory", embedding_dim=3072)
await store.connect()

markdown_store = MarkdownMemoryStore("/shared/memory")

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-large",
    embedding_dimension=3072,
    llm_for_extraction="gpt-4o-mini",
    markdown_store=markdown_store,
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

### Session Lifecycle
```yaml
# Reset sessions daily at 4am UTC
SESSION_DAILY_RESET_HOUR: 4

# Reset after 60 minutes of inactivity
SESSION_IDLE_TIMEOUT_MINUTES: 60
```

### Transcript Indexing
```yaml
# Enable to allow searching across past session transcripts
TRANSCRIPT_INDEXING_ENABLED: true
```

This chunks transcripts into ~400-token segments with 80-token overlap and stores them in LanceDB. Increases storage but enables cross-session semantic search.

## Embedding Models

| Model | Dimension | Cost/1M tokens | Use Case |
|-------|-----------|----------------|----------|
| text-embedding-3-large | 3072 | $0.13 | Production |
| text-embedding-3-small | 1536 | $0.02 | Development |
| text-embedding-ada-002 | 1536 | $0.10 | Legacy |

## Storage Layout

```
data/sandbox-data/shared/memory/    # Markdown source of truth (agent-accessible)
  MEMORY.md                         # Curated long-term memory
  2026-02-08.md                     # Daily logs

.suzent/
  memory/                           # LanceDB search index
  transcripts/{session_id}.jsonl    # Session transcripts
  state/{session_id}.json           # Agent state snapshots
  chats.db                          # SQLite metadata
```

## Recovery

### Rebuild LanceDB from Markdown

If the LanceDB index is corrupted or lost:

```python
from suzent.memory import MarkdownIndexer

indexer = MarkdownIndexer()
stats = await indexer.reindex_from_markdown(
    markdown_store=manager.markdown_store,
    lancedb_store=manager.store,
    embedding_gen=manager.embedding_gen,
    user_id="default-user",
    clear_existing=True,
)
print(f"Indexed {stats['indexed']} facts from {stats['total_files']} files")
```

Or via the API:

```bash
curl -X POST http://localhost:25314/memory/reindex \
  -H "Content-Type: application/json" \
  -d '{"clear_existing": true}'
```

## Debug Logging

```bash
LOG_LEVEL=DEBUG uv run suzent
```
