# Troubleshooting

## Vector Dimension Mismatch

**Error:** `ERROR: expected 1536 dimensions, not 3072`

**Cause:** Embedding model dimension doesn't match database.

**Solution:**
```sql
-- Check current
\d+ archival_memories

-- Alter table
ALTER TABLE archival_memories ALTER COLUMN embedding TYPE vector(3072);

-- Rebuild index
DROP INDEX idx_archival_memories_embedding;
CREATE INDEX idx_archival_memories_embedding ON archival_memories
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ANALYZE archival_memories;
```

## Slow Search

**Symptoms:** Search taking >1 second

**Diagnosis:**
```sql
EXPLAIN ANALYZE
SELECT * FROM archival_memories
ORDER BY embedding <=> '[...]'::vector
LIMIT 10;

-- Should show "Index Scan", not "Seq Scan"
```

**Solutions:**

1. **Check index exists:**
```sql
\d archival_memories
```

2. **Increase lists:**
```sql
DROP INDEX idx_archival_memories_embedding;
CREATE INDEX idx_archival_memories_embedding ON archival_memories
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 500);
```

3. **Update statistics:**
```sql
ANALYZE archival_memories;
```

4. **Vacuum:**
```sql
VACUUM ANALYZE archival_memories;
```

## No Memories Extracted

**Checks:**

1. **LLM configured?**
```python
manager = MemoryManager(
    store=store,
    llm_for_extraction="gpt-4o-mini"  # Must be set
)
```

2. **Processing user messages?**
```python
# Only extracts from role="user"
message = {"role": "user", "content": "..."}
```

3. **API key set?**
```bash
echo $OPENAI_API_KEY
```

4. **Debug logging:**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

5. **Check report:**
```python
report = await manager.process_message_for_memories(...)
print(report)  # Check 'extracted_facts'
```

## Connection Pool Exhausted

**Error:** `asyncpg.exceptions.TooManyConnectionsError`

**Solutions:**

1. **Increase pool:**
```python
store = PostgresMemoryStore(
    connection_string,
    max_size=50  # Increase
)
```

2. **Close connections:**
```python
try:
    await store.connect()
    # ...
finally:
    await store.close()
```

3. **Check active:**
```sql
SELECT count(*) FROM pg_stat_activity
WHERE datname = 'suzent';
```

## High Memory Usage

**Check size:**
```sql
SELECT pg_size_pretty(pg_total_relation_size('archival_memories'));
```

**Solutions:**

1. **Vacuum:**
```sql
VACUUM FULL archival_memories;
```

2. **Prune old memories:**
```python
# Delete low-importance old memories
await store.execute("""
    DELETE FROM archival_memories
    WHERE created_at < NOW() - INTERVAL '1 year'
        AND importance < 0.3
        AND access_count < 5
""")
```

## Connection Failed

**Error:** `Connection refused`

**Check:**
```bash
docker ps
docker logs suzent-postgres
```

**Fix:**
```bash
docker start suzent-postgres
```

## Schema Not Found

**Error:** `relation "archival_memories" does not exist`

**Run setup:**
```bash
./scripts/setup_memory_db.sh
```

Or manually:
```bash
psql -U suzent -h localhost -p 5430 -d suzent < src/suzent/memory/schema.sql
```

## Import Errors

**Error:** `ModuleNotFoundError: No module named 'suzent.memory'`

**Install:**
```bash
uv sync
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

## Debug Commands

```sql
-- Check tables
\dt

-- Check indexes
\di

-- Check table size
SELECT pg_size_pretty(pg_relation_size('archival_memories'));

-- Check index size
SELECT pg_size_pretty(pg_indexes_size('archival_memories'));

-- Check dead tuples
SELECT n_live_tup, n_dead_tup FROM pg_stat_user_tables
WHERE tablename = 'archival_memories';

-- Check slow queries
SELECT * FROM pg_stat_statements
ORDER BY total_time DESC LIMIT 10;
```

## Getting Help

1. Enable debug logging
2. Check logs for errors
3. Run diagnostic queries
4. Open issue with: error message, config, logs

