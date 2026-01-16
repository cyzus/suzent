"""
PostgreSQL store with pgvector for memory management.
"""

import asyncpg
from pgvector.asyncpg import register_vector
from typing import List, Dict, Any, Optional
import json

from suzent.logger import get_logger

logger = get_logger(__name__)


class PostgresMemoryStore:
    """PostgreSQL store with pgvector for memory management."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self.pool: Optional[asyncpg.Pool] = None

    async def _setup_vector_type(self, conn):
        """Register pgvector type for a connection."""
        await register_vector(conn)

    async def connect(self):
        """Initialize connection pool."""
        try:
            self.pool = await asyncpg.create_pool(
                self.connection_string,
                min_size=2,
                max_size=10,
                command_timeout=60,
                init=self._setup_vector_type,
            )
            logger.info("PostgreSQL connection pool created")

            # Ensure extensions are enabled
            async with self.pool.acquire() as conn:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                logger.info("PostgreSQL extensions enabled (vector, pg_trgm)")

        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    # ===== Core Memory Block Operations =====

    async def get_memory_block(
        self, label: str, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> Optional[str]:
        """Get a core memory block."""
        async with self.pool.acquire() as conn:
            content = await conn.fetchval(
                """
                SELECT content FROM memory_blocks
                WHERE
                    label = $1
                    AND (chat_id IS NULL OR chat_id = $2)
                    AND (user_id IS NULL OR user_id = $3)
                ORDER BY created_at DESC
                LIMIT 1
            """,
                label,
                chat_id,
                user_id,
            )
            return content

    async def get_all_memory_blocks(
        self, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get all core memory blocks as a dictionary."""
        try:
            if not self.pool:
                logger.error("PostgreSQL pool is None - connection not established")
                return {}

            async with self.pool.acquire() as conn:
                # Priority: chat-specific > user-level > global (NULL user_id)
                # Within each tier, most recent wins
                rows = await conn.fetch(
                    """
                    SELECT DISTINCT ON (label) label, content
                    FROM memory_blocks
                    WHERE
                        (chat_id IS NULL OR chat_id = $1)
                        AND (user_id IS NULL OR user_id = $2)
                    ORDER BY 
                        label,
                        CASE 
                            WHEN chat_id = $1 THEN 1
                            WHEN chat_id IS NULL THEN 2
                            ELSE 3
                        END,
                        CASE
                            WHEN user_id = $2 THEN 1
                            WHEN user_id IS NULL THEN 2
                            ELSE 3
                        END,
                        created_at DESC
                """,
                    chat_id,
                    user_id,
                )

                return {row["label"]: row["content"] for row in rows}
        except Exception as e:
            logger.error(f"Error fetching memory blocks: {e}")
            return {}

    async def set_memory_block(
        self,
        label: str,
        content: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Set or update a core memory block."""
        async with self.pool.acquire() as conn:
            # Use a simpler conflict resolution
            await conn.execute(
                """
                INSERT INTO memory_blocks (label, content, chat_id, user_id, created_at, updated_at)
                VALUES ($1, $2, $3, $4, NOW(), NOW())
                ON CONFLICT (label, COALESCE(chat_id, ''), COALESCE(user_id, ''))
                DO UPDATE SET content = $2, updated_at = NOW()
            """,
                label,
                content,
                chat_id,
                user_id,
            )
            return True

    # ===== Archival Memory Operations =====

    async def add_memory(
        self,
        content: str,
        embedding: List[float],
        user_id: str,
        chat_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> str:
        """Add a memory with vector embedding."""
        async with self.pool.acquire() as conn:
            try:
                memory_id = await conn.fetchval(
                    """
                    INSERT INTO archival_memories
                    (content, embedding, user_id, chat_id, metadata, importance, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, CAST($5 AS jsonb), $6, NOW(), NOW())
                    RETURNING id
                """,
                    content,
                    embedding,
                    user_id,
                    chat_id,
                    json.dumps(metadata or {}),
                    importance,
                )

                return str(memory_id)
            except asyncpg.DataError as de:
                # Common cause: pgvector dimension mismatch (e.g. DB vector(1536) but model produced 3072)
                msg = str(de)
                logger.error(f"Vector dimension mismatch inserting memory: {msg}")
                # Provide an actionable error to the caller
                raise ValueError(
                    f"Embedding dimension mismatch when inserting memory: {msg}.\n"
                    "This usually means your embedding model returns a different vector size than the `archival_memories.embedding` column.\n"
                    "Options:\n"
                    "  * Use an embedding model whose dimension matches your DB (set EMBEDDING_MODEL in config).\n"
                    "  * Alter your DB column to the new dimension, e.g.:\n"
                    "      ALTER TABLE archival_memories ALTER COLUMN embedding TYPE vector(<new_dim>);\n"
                    "  * Recreate the database schema using `memory/schema.sql` after updating the vector size.\n"
                ) from de

    async def semantic_search(
        self,
        query_embedding: List[float],
        user_id: str,
        limit: int = 10,
        chat_id: Optional[str] = None,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Pure semantic search using vector similarity."""
        async with self.pool.acquire() as conn:
            # Handle NULL chat_id - if None, don't filter by chat_id at all
            if chat_id is None:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        content,
                        metadata,
                        importance,
                        created_at,
                        updated_at,
                        access_count,
                        1 - (embedding <=> $1) AS similarity
                    FROM archival_memories
                    WHERE
                        user_id = $2
                        AND importance >= $3
                    ORDER BY embedding <=> $1
                    LIMIT $4
                """,
                    query_embedding,
                    user_id,
                    min_importance,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        id,
                        content,
                        metadata,
                        importance,
                        created_at,
                        updated_at,
                        access_count,
                        1 - (embedding <=> $1) AS similarity
                    FROM archival_memories
                    WHERE
                        user_id = $2
                        AND (chat_id = $3 OR chat_id IS NULL)
                        AND importance >= $4
                    ORDER BY embedding <=> $1
                    LIMIT $5
                """,
                    query_embedding,
                    user_id,
                    chat_id,
                    min_importance,
                    limit,
                )

            results = [dict(row) for row in rows]

            # Update access stats for retrieved memories
            if results:
                memory_ids = [r["id"] for r in results]
                await conn.execute(
                    """
                    UPDATE archival_memories
                    SET accessed_at = NOW(), access_count = access_count + 1
                    WHERE id = ANY($1)
                """,
                    memory_ids,
                )

            return results

    async def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        user_id: str,
        limit: int = 10,
        chat_id: Optional[str] = None,
        semantic_weight: float = 0.7,
        fts_weight: float = 0.3,
        recency_boost: float = 0.1,
        importance_boost: float = 0.2,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining:
        - Semantic similarity (vector)
        - Full-text search (tsvector)
        - Recency boost
        - Importance boost
        """
        async with self.pool.acquire() as conn:
            # Handle NULL chat_id - if None, don't filter by chat_id at all
            if chat_id is None:
                rows = await conn.fetch(
                    """
                    WITH semantic AS (
                        SELECT
                            id,
                            content,
                            metadata,
                            importance,
                            created_at,
                            updated_at,
                            access_count,
                            1 - (embedding <=> $1) AS semantic_score
                        FROM archival_memories
                        WHERE user_id = $2
                        ORDER BY embedding <=> $1
                        LIMIT 50
                    ),
                    fulltext AS (
                        SELECT
                            id,
                            ts_rank(content_fts, websearch_to_tsquery('english', $3)) AS fts_score
                        FROM archival_memories
                        WHERE
                            user_id = $2
                            AND content_fts @@ websearch_to_tsquery('english', $3)
                    )
                    SELECT
                        s.id,
                        s.content,
                        s.metadata,
                        s.importance,
                        s.created_at,
                        s.updated_at,
                        s.access_count,
                        s.semantic_score,
                        COALESCE(f.fts_score, 0) AS fts_score,
                        EXTRACT(EPOCH FROM (NOW() - s.created_at)) / 86400 AS age_days,
                        (
                            s.semantic_score * $4 +
                            COALESCE(f.fts_score, 0) * $5 +
                            s.importance * $6 +
                            (1.0 / (1.0 + EXTRACT(EPOCH FROM (NOW() - s.created_at)) / 86400)) * $7
                        ) AS combined_score
                    FROM semantic s
                    LEFT JOIN fulltext f ON s.id = f.id
                    ORDER BY combined_score DESC
                    LIMIT $8
                """,
                    query_embedding,
                    user_id,
                    query_text,
                    semantic_weight,
                    fts_weight,
                    importance_boost,
                    recency_boost,
                    limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    WITH semantic AS (
                        SELECT
                            id,
                            content,
                            metadata,
                            importance,
                            created_at,
                            updated_at,
                            access_count,
                            1 - (embedding <=> $1) AS semantic_score
                        FROM archival_memories
                        WHERE user_id = $2 AND (chat_id = $3 OR chat_id IS NULL)
                        ORDER BY embedding <=> $1
                        LIMIT 50
                    ),
                    fulltext AS (
                        SELECT
                            id,
                            ts_rank(content_fts, websearch_to_tsquery('english', $4)) AS fts_score
                        FROM archival_memories
                        WHERE
                            user_id = $2
                            AND (chat_id = $3 OR chat_id IS NULL)
                            AND content_fts @@ websearch_to_tsquery('english', $4)
                    )
                    SELECT
                        s.id,
                        s.content,
                        s.metadata,
                        s.importance,
                        s.created_at,
                        s.updated_at,
                        s.access_count,
                        s.semantic_score,
                        COALESCE(f.fts_score, 0) AS fts_score,
                        EXTRACT(EPOCH FROM (NOW() - s.created_at)) / 86400 AS age_days,
                        (
                            s.semantic_score * $5 +
                            COALESCE(f.fts_score, 0) * $6 +
                            s.importance * $7 +
                            (1.0 / (1.0 + EXTRACT(EPOCH FROM (NOW() - s.created_at)) / 86400)) * $8
                        ) AS combined_score
                    FROM semantic s
                    LEFT JOIN fulltext f ON s.id = f.id
                    ORDER BY combined_score DESC
                    LIMIT $9
                """,
                    query_embedding,
                    user_id,
                    chat_id,
                    query_text,
                    semantic_weight,
                    fts_weight,
                    importance_boost,
                    recency_boost,
                    limit,
                )

            results = [dict(row) for row in rows]

            # Update access stats
            if results:
                memory_ids = [r["id"] for r in results]
                await conn.execute(
                    """
                    UPDATE archival_memories
                    SET accessed_at = NOW(), access_count = access_count + 1
                    WHERE id = ANY($1)
                """,
                    memory_ids,
                )

            return results

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
    ) -> bool:
        """Update memory content and/or embedding atomically."""
        async with self.pool.acquire() as conn:
            # Build dynamic update query
            updates = ["updated_at = NOW()"]
            params = []
            param_idx = 1

            if content is not None:
                updates.append(f"content = ${param_idx}")
                params.append(content)
                param_idx += 1

            if embedding is not None:
                updates.append(f"embedding = ${param_idx}")
                params.append(embedding)
                param_idx += 1

            if metadata is not None:
                updates.append(f"metadata = CAST(${param_idx} AS jsonb)")
                params.append(json.dumps(metadata))
                param_idx += 1

            if importance is not None:
                updates.append(f"importance = ${param_idx}")
                params.append(importance)
                param_idx += 1

            params.append(memory_id)

            result = await conn.execute(
                f"""
                UPDATE archival_memories
                SET {", ".join(updates)}
                WHERE id = ${param_idx}::uuid
            """,
                *params,
            )

            return result == "UPDATE 1"

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM archival_memories WHERE id = $1
            """,
                memory_id,
            )
            return result == "DELETE 1"

    async def delete_all_memories(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> int:
        """Delete all memories for a user/chat."""
        async with self.pool.acquire() as conn:
            if chat_id is None:
                result = await conn.execute(
                    """
                    DELETE FROM archival_memories WHERE user_id = $1
                """,
                    user_id,
                )
            else:
                result = await conn.execute(
                    """
                    DELETE FROM archival_memories WHERE user_id = $1 AND chat_id = $2
                """,
                    user_id,
                    chat_id,
                )
            # Parse result like "DELETE 5"
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Deleted {count} archival memories for user {user_id}")
            return count

    async def delete_all_memory_blocks(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> int:
        """Delete all memory blocks for a user/chat."""
        async with self.pool.acquire() as conn:
            if chat_id is None:
                result = await conn.execute(
                    """
                    DELETE FROM memory_blocks WHERE user_id = $1 OR user_id IS NULL
                """,
                    user_id,
                )
            else:
                result = await conn.execute(
                    """
                    DELETE FROM memory_blocks WHERE (user_id = $1 OR user_id IS NULL) AND (chat_id = $2 OR chat_id IS NULL)
                """,
                    user_id,
                    chat_id,
                )
            count = int(result.split()[-1]) if result else 0
            logger.info(f"Deleted {count} memory blocks for user {user_id}")
            return count

    async def get_memory_count(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> int:
        """Get total number of memories for a user."""
        async with self.pool.acquire() as conn:
            if chat_id is None:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM archival_memories
                    WHERE user_id = $1
                """,
                    user_id,
                )
            else:
                count = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM archival_memories
                    WHERE user_id = $1 AND chat_id = $2
                """,
                    user_id,
                    chat_id,
                )
            return count

    async def list_memories(
        self,
        user_id: str,
        chat_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> List[Dict[str, Any]]:
        """List memories with pagination and ordering."""
        # Validate order_by column to prevent SQL injection
        valid_columns = ["created_at", "importance", "access_count", "accessed_at"]
        if order_by not in valid_columns:
            order_by = "created_at"

        order_direction = "DESC" if order_desc else "ASC"

        async with self.pool.acquire() as conn:
            if chat_id is None:
                query = f"""
                    SELECT
                        id,
                        content,
                        metadata,
                        importance,
                        created_at,
                        updated_at,
                        access_count,
                        accessed_at
                    FROM archival_memories
                    WHERE user_id = $1
                    ORDER BY {order_by} {order_direction}
                    LIMIT $2 OFFSET $3
                """
                rows = await conn.fetch(query, user_id, limit, offset)
            else:
                query = f"""
                    SELECT
                        id,
                        content,
                        metadata,
                        importance,
                        created_at,
                        updated_at,
                        access_count,
                        accessed_at
                    FROM archival_memories
                    WHERE user_id = $1 AND chat_id = $2
                    ORDER BY {order_by} {order_direction}
                    LIMIT $3 OFFSET $4
                """
                rows = await conn.fetch(query, user_id, chat_id, limit, offset)

            return [dict(row) for row in rows]

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get memory statistics for a user."""
        async with self.pool.acquire() as conn:
            stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) as total_memories,
                    AVG(importance) as avg_importance,
                    MAX(importance) as max_importance,
                    MIN(importance) as min_importance,
                    SUM(access_count) as total_accesses,
                    AVG(access_count) as avg_access_count
                FROM archival_memories
                WHERE user_id = $1
            """,
                user_id,
            )

            # Get importance distribution
            distribution = await conn.fetch(
                """
                SELECT
                    CASE
                        WHEN importance >= 0.8 THEN 'high'
                        WHEN importance >= 0.5 THEN 'medium'
                        ELSE 'low'
                    END as category,
                    COUNT(*) as count
                FROM archival_memories
                WHERE user_id = $1
                GROUP BY category
            """,
                user_id,
            )

            return {
                "total_memories": stats["total_memories"] or 0,
                "avg_importance": float(stats["avg_importance"])
                if stats["avg_importance"]
                else 0.0,
                "max_importance": float(stats["max_importance"])
                if stats["max_importance"]
                else 0.0,
                "min_importance": float(stats["min_importance"])
                if stats["min_importance"]
                else 0.0,
                "total_accesses": stats["total_accesses"] or 0,
                "avg_access_count": float(stats["avg_access_count"])
                if stats["avg_access_count"]
                else 0.0,
                "importance_distribution": {
                    row["category"]: row["count"] for row in distribution
                },
            }
