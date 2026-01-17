# Configuration

## Environment Variables

### Database
```bash
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5430
POSTGRES_DB=suzent
POSTGRES_USER=suzent
POSTGRES_PASSWORD=password
```

### Embedding
```bash
EMBEDDING_MODEL=text-embedding-3-large  # or text-embedding-3-small
EMBEDDING_DIMENSION=3072                # Auto-detected if omitted
```

### Extraction (Optional)
```bash
MEMORY_EXTRACTION_MODEL=gpt-4o-mini    # Enables automatic extraction
```

### API Keys
```bash
OPENAI_API_KEY=sk-xxx
```

## Manager Initialization

```python
from suzent.memory import MemoryManager, PostgresMemoryStore

connection_string = f"postgresql://{user}:{password}@{host}:{port}/{db}"

store = PostgresMemoryStore(connection_string)
await store.connect()

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-large",
    embedding_dimension=3072,  # Optional
    llm_for_extraction="gpt-4o-mini"  # Optional
)
```

## Connection Pool

```python
store = PostgresMemoryStore(
    connection_string,
    min_size=2,
    max_size=10,
    command_timeout=60
)
```

**Recommendations:**
- Dev: min=1, max=5
- Prod: min=5, max=20
- High traffic: min=10, max=50

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

## Changing Embedding Model

1. Update environment:
```bash
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

2. Alter database:
```sql
ALTER TABLE archival_memories ALTER COLUMN embedding TYPE vector(1536);
DROP INDEX idx_archival_memories_embedding;
CREATE INDEX idx_archival_memories_embedding ON archival_memories
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

3. Optional: Clear old embeddings:
```sql
TRUNCATE archival_memories;
```

## Docker Compose

```yaml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg18
    environment:
      POSTGRES_USER: suzent
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: suzent
    ports:
      - "5430:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql

volumes:
  postgres_data:
```

Start: `docker-compose up -d`

## Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
