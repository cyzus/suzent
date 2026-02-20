# Troubleshooting

## Storage Issues

### Permission Denied Errors

**Error:** `PermissionError: [Errno 13] Permission denied: '.suzent/data/memory'`

**Cause:** Insufficient permissions to create or access LanceDB storage directory.

**Solution:**
```bash
# Check directory permissions
ls -la .suzent/data/

# Fix permissions (Linux/Mac)
chmod -R 755 .suzent/data/memory

# Windows: Right-click folder → Properties → Security → Edit permissions
```

### Storage Not Found

**Error:** `Directory not found` or initialization failures

**Cause:** LanceDB URI path doesn't exist or is misconfigured.

**Solution:**
```python
from pathlib import Path

# Ensure directory exists
storage_path = Path(".suzent/data/memory")
storage_path.mkdir(parents=True, exist_ok=True)

# Then initialize store
store = LanceDBMemoryStore(uri=str(storage_path))
```

## Vector Dimension Mismatch

**Error:** `Dimension mismatch: expected 3072, got 1536`

**Cause:** Embedding model dimension doesn't match configured dimension.

**Solution:**
```python
# Option 1: Update config to match model
# If using text-embedding-3-small (1536 dimensions)
store = LanceDBMemoryStore(
    uri=".suzent/data/memory",
    embedding_dim=1536
)

manager = MemoryManager(
    store=store,
    embedding_model="text-embedding-3-small",
    embedding_dimension=1536
)

# Option 2: Clear existing data and rebuild
# Delete the storage directory
import shutil
shutil.rmtree(".suzent/data/memory")
# Reinitialize with correct dimensions
```

## Slow Search Performance

**Symptoms:** Search taking >2 seconds

**Diagnosis:**
1. Check table size:
```python
from pathlib import Path

db_path = Path(".suzent/data/memory")
total_size = sum(f.stat().st_size for f in db_path.rglob('*') if f.is_file())
print(f"Storage size: {total_size / (1024**2):.2f} MB")

# Count memories
count = await store.get_memory_count(user_id="your-user-id")
print(f"Total memories: {count}")
```

2. Check if search parameters are too broad:
```python
# Use stricter filters
results = await manager.search_memories(
    query="...",
    user_id="specific-user",
    chat_id="specific-chat",  # Add chat scope
    limit=5  # Reduce limit
)
```

**Solutions:**

1. **Optimize search parameters:**
```python
# Use hybrid search with adjusted weights
results = await store.hybrid_search(
    query_embedding=embedding,
    query_text=query,
    user_id=user_id,
    limit=10,
    semantic_weight=0.8,  # Prioritize vector search
    fts_weight=0.2
)
```

2. **Compact storage:**
```python
# LanceDB automatically optimizes, but you can force cleanup
# by deleting and rebuilding storage if needed
```

## No Memories Extracted

**Checks:**

1. **LLM configured?**
```python
manager = MemoryManager(
    store=store,
    llm_for_extraction="gpt-4o-mini"  # Must be set for LLM extraction
)
```

2. **Memory system enabled?**
```python
from suzent.config import CONFIG
print(f"Memory enabled: {CONFIG.memory_enabled}")
print(f"Extraction model: {CONFIG.extraction_model}")
```

3. **Processing conversation turns?**
```python
# Ensure you're using process_conversation_turn_for_memories
from suzent.memory.models import ConversationTurn, Message

turn = ConversationTurn(
    user_message=Message(role="user", content="..."),
    assistant_message=Message(role="assistant", content="..."),
    agent_actions=[...]
)

result = await manager.process_conversation_turn_for_memories(
    conversation_turn=turn,
    chat_id="chat-id",
    user_id="user-id"
)
print(f"Extracted: {result.extracted_facts}")
```

4. **API key set?**
```bash
echo $OPENAI_API_KEY
```

5. **Debug logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Storage Size Issues

### High Disk Usage

**Check size:**
```python
from pathlib import Path

db_path = Path(".suzent/data/memory")
total_size = sum(f.stat().st_size for f in db_path.rglob('*') if f.is_file())
print(f"Memory storage: {total_size / (1024**2):.2f} MB")
```

**Solutions:**

1. **Delete old low-importance memories:**
```python
# Get all memories sorted by importance
memories = await store.list_memories(
    user_id="user-id",
    order_by="importance",
    order_desc=False,  # Lowest first
    limit=100
)

# Delete low-importance old memories
for mem in memories:
    if mem['importance'] < 0.3 and mem['access_count'] < 2:
        await store.delete_memory(mem['id'])
```

2. **Clear all memories for a user:**
```python
await store.delete_all_memories(user_id="user-id")
```

3. **Clear entire storage:**
```python
import shutil
shutil.rmtree(".suzent/data/memory")
# Reinitialize
store = LanceDBMemoryStore(uri=".suzent/data/memory")
await store.connect()
```

## Import Errors

**Error:** `ModuleNotFoundError: No module named 'suzent.memory'`

**Install:**
```bash
uv sync
# or
pip install -e .
```

## Embedding Generation Fails

**Error:** `OpenAI API error`

**Checks:**
1. API key valid
2. Billing enabled
3. Rate limits not exceeded
4. Network connectivity

**Retry with backoff:**
```python
from tenacity import retry, wait_exponential

@retry(wait=wait_exponential(multiplier=1, min=2, max=10))
async def generate_with_retry(text):
    return await embedding_gen.generate(text)
```

## Connection/Initialization Errors

**Error:** `Failed to initialize memory system`

**Debug:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)

from suzent.memory import init_memory_system

# Check initialization
success = await init_memory_system()
print(f"Memory system initialized: {success}")
```

**Common causes:**
- Storage path not writable
- Embedding dimension mismatch
- Missing dependencies (lancedb, pyarrow)
- Configuration errors

**Fix dependencies:**
```bash
pip install lancedb pyarrow
```

## Data Migration

### Moving from PostgreSQL to LanceDB

If you have existing PostgreSQL data:

```python
# Export from PostgreSQL
old_store = PostgresMemoryStore(connection_string)
await old_store.connect()
memories = await old_store.list_memories(user_id="user-id", limit=10000)

# Import to LanceDB
new_store = LanceDBMemoryStore(uri=".suzent/data/memory")
await new_store.connect()

for mem in memories:
    await new_store.add_memory(
        content=mem['content'],
        embedding=mem['embedding'],
        user_id=mem['user_id'],
        chat_id=mem.get('chat_id'),
        metadata=mem.get('metadata', {}),
        importance=mem.get('importance', 0.5)
    )
```

## Getting Help

1. Enable debug logging
2. Check logs for errors
3. Verify configuration matches documentation
4. Open issue with: error message, config, logs

