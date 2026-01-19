"""
Migration script to move memory data from PostgreSQL to LanceDB.

Usage:
    python scripts/migrate_memory.py

Requirements:
    pip install asyncpg lancedb
"""

import asyncio
import os
import json
import asyncpg
import lancedb
from datetime import datetime
from suzent.config import CONFIG
from suzent.memory.lancedb_store import LanceDBMemoryStore

# Postgres Config
PG_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
PG_PORT = os.getenv("POSTGRES_PORT", "5430")
PG_DB = os.getenv("POSTGRES_DB", "suzent")
PG_USER = os.getenv("POSTGRES_USER", "suzent")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "ultra_secret")
PG_CONN = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

async def migrate():
    print("Starting migration from Postgres to LanceDB...")
    
    # 1. Connect to Postgres
    try:
        pg_pool = await asyncpg.create_pool(PG_CONN)
        print("Connected to PostgreSQL.")
    except Exception as e:
        print(f"Failed to connect to Postgres: {e}")
        return

    # 2. Connect to LanceDB
    lancedb_store = LanceDBMemoryStore(CONFIG.lancedb_uri)
    await lancedb_store.connect()
    print(f"Connected to LanceDB at {CONFIG.lancedb_uri}")

    # 3. Migrate Memory Blocks
    print("\n--- Migrating Memory Blocks ---")
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT label, content, chat_id, user_id, created_at, updated_at FROM memory_blocks")
        print(f"Found {len(rows)} memory blocks.")
        
        count = 0
        for row in rows:
            # We use set_memory_block logic but manually insert to preserve timestamps if possible?
            # actually set_memory_block overwrites ts.
            # Let's use internal table add to preserve TS if we care, or just set_memory_block
            # For blocks, recency is key, so maybe just set it.
            # But wait, LanceDBStore `set_memory_block` creates new datetime.now().
            # If we want to preserve historical blocks, we might need a lower level insert.
            # However, blocks are "current state", so maybe ok to refresh ts?
            # Actually, `get_memory_block` sorts by created_at. So we SHOULD preserve it.
            
            # Using table direct access
            from suzent.memory.lancedb_store import MemoryBlockModel
            
            block = MemoryBlockModel(
                label=row['label'],
                content=row['content'],
                chat_id=row['chat_id'],
                user_id=row['user_id'],
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            await lancedb_store.blocks_table.add([block])
            count += 1
            
        print(f"Migrated {count} memory blocks.")

    # 4. Migrate Archival Memories
    print("\n--- Migrating Archival Memories ---")
    async with pg_pool.acquire() as conn:
        # Postgres vector is returned as string or list? asyncpg with pgvector returns list/array
        # We need to make sure we cast or handle it. register_vector usually handles it.
        # But we didn't register it on this pool.
        from pgvector.asyncpg import register_vector
        await register_vector(conn)
        
        rows = await conn.fetch("""
            SELECT id, content, embedding, user_id, chat_id, metadata, importance, created_at, updated_at, accessed_at, access_count 
            FROM archival_memories
        """)
        print(f"Found {len(rows)} archival memories.")
        
        from suzent.memory.lancedb_store import ArchivalMemoryModel
        
        batch = []
        for row in rows:
            # Metadata in PG is JSONB (dict), Model expects JSON string?
            # Let's check lancedb_store model definition. 
            # `metadata: str` (JSON string).
            # PG row['metadata'] is dict (via asyncpg jsonb).
            # So dump it.
            
            meta_str = json.dumps(row['metadata']) if row['metadata'] else "{}"
            
            mem = ArchivalMemoryModel(
                id=str(row['id']),
                content=row['content'],
                vector=row['embedding'], # asyncpg returns list[float]
                user_id=row['user_id'],
                chat_id=row['chat_id'],
                metadata=meta_str,
                importance=float(row['importance']),
                created_at=row['created_at'],
                updated_at=row['updated_at'],
                accessed_at=row['accessed_at'],
                access_count=row['access_count']
            )
            batch.append(mem)
            
        if batch:
            await lancedb_store.archival_table.add(batch)
            
        print(f"Migrated {len(batch)} archival memories.")

    print("\nMigration complete.")
    await pg_pool.close()
    await lancedb_store.close()

if __name__ == "__main__":
    asyncio.run(migrate())
