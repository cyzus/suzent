# Database Schema

## Tables

### memory_blocks
Structured working memory (always visible).

```sql
CREATE TABLE memory_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id TEXT,
    user_id TEXT,
    label TEXT NOT NULL CHECK (label IN ('persona', 'user', 'facts', 'context')),
    content TEXT NOT NULL,
    max_size INTEGER DEFAULT 2048,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_memory_blocks_unique_label
ON memory_blocks (label, COALESCE(chat_id, ''), COALESCE(user_id, ''));
```

**Scoping:** Chat-specific > user-level > global (NULL)

### archival_memories
Long-term storage with vector embeddings.

```sql
CREATE TABLE archival_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id TEXT,
    user_id TEXT,
    content TEXT NOT NULL,
    embedding vector(3072),
    metadata JSONB DEFAULT '{}'::jsonb,
    importance REAL DEFAULT 0.5 CHECK (importance >= 0 AND importance <= 1),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    accessed_at TIMESTAMPTZ,
    access_count INTEGER DEFAULT 0,
    content_fts tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED
);
```

**Metadata Structure (`conversation_context`):**
The `metadata` JSONB field stores rich context about the memory:
```json
{
  "importance": 0.8,
  "category": "technical",
  "tags": ["react", "optimization"],
  "source_chat_id": "uuid",
  "conversation_context": {
    "user_intent": "User wanted to fix slow dashboard",
    "agent_actions_summary": "Searched for react performance tools",
    "outcome": "Recommended react-window"
  }
}
```

**Indexes:**
```sql
-- Vector search (IVFFlat for 3072-dim)
CREATE INDEX idx_archival_memories_embedding ON archival_memories
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Full-text search
CREATE INDEX idx_archival_memories_fts ON archival_memories USING GIN(content_fts);

-- Standard indexes
CREATE INDEX idx_archival_memories_user_id ON archival_memories(user_id);
CREATE INDEX idx_archival_memories_importance ON archival_memories(importance DESC);
```

**Lists Parameter:**
- <10K memories: lists=100
- 10K-100K: lists=500
- 100K-1M: lists=1000
- >1M: lists=2000

### memory_relationships
Semantic relationships (schema defined, not yet implemented).

```sql
CREATE TABLE memory_relationships (
    id SERIAL PRIMARY KEY,
    source_id UUID REFERENCES archival_memories(id) ON DELETE CASCADE,
    target_id UUID REFERENCES archival_memories(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,  -- 'related', 'conflicts_with', 'supersedes'
    strength REAL DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Triggers

Auto-update timestamps:

```sql
CREATE FUNCTION update_updated_at_column() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_memory_blocks_updated_at
BEFORE UPDATE ON memory_blocks
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_archival_memories_updated_at
BEFORE UPDATE ON archival_memories
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

## Maintenance

### Statistics
```sql
ANALYZE archival_memories;
ANALYZE memory_blocks;
```

### Vacuum
```sql
VACUUM ANALYZE archival_memories;
```

### Index Rebuild
```sql
REINDEX INDEX idx_archival_memories_embedding;
```

### Monitor Index Usage
```sql
SELECT indexname, idx_scan
FROM pg_stat_user_indexes
WHERE schemaname = 'public';
```

## Backup

```bash
# Full backup
pg_dump -U suzent -h localhost -p 5430 suzent > backup.sql

# Compressed
pg_dump -U suzent -h localhost -p 5430 suzent | gzip > backup.sql.gz

# Restore
psql -U suzent -h localhost -p 5430 suzent < backup.sql
```

## Migration: Change Embedding Dimension

```sql
-- 1. Backup
CREATE TABLE archival_memories_backup AS SELECT * FROM archival_memories;

-- 2. Alter
ALTER TABLE archival_memories ALTER COLUMN embedding TYPE vector(1536);

-- 3. Rebuild index
DROP INDEX idx_archival_memories_embedding;
CREATE INDEX idx_archival_memories_embedding ON archival_memories
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- 4. Analyze
ANALYZE archival_memories;

-- 5. Drop backup if successful
DROP TABLE archival_memories_backup;
```

