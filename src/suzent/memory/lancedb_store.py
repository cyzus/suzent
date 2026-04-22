"""
LanceDB memory store implementation.

This module provides a LanceDB-based backend for Suzent's memory system,
offering both semantic (vector) and full-text search capabilities for
memory blocks and archival memories.

Features:
- Core memory blocks (key-value storage with user/chat scoping)
- Archival memories with vector embeddings for semantic search
- Hybrid search combining semantic similarity, FTS, recency, and importance
- Full SQL injection protection via escaping
- Timezone-aware datetime handling
"""

import asyncio
import json
import os
import statistics
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import lancedb
from lancedb.index import FTS
from lancedb.pydantic import LanceModel, Vector

from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)


# --- Constants ---

CHAT_MATCH_BONUS = 10
USER_MATCH_BONUS = 5


# --- Helper Functions ---


def _escape_sql(value: Optional[str]) -> str:
    """Escape SQL string literals to prevent injection."""
    if value is None:
        return "NULL"
    return value.replace("'", "''")


def _utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


# --- Data Classes ---


@dataclass
class ScoredResult:
    """Helper for hybrid search scoring."""

    doc: Dict[str, Any]
    sem_score: float = 0.0
    fts_score: float = 0.0

    def calculate_final_score(
        self, sem_weight: float, fts_weight: float, imp_boost: float, rec_boost: float
    ) -> float:
        """Calculate weighted final score."""
        imp = self.doc["importance"]

        # Handle both timezone-aware and timezone-naive datetimes
        created_at = self.doc["created_at"]
        if created_at.tzinfo is None:
            # Make naive datetime UTC-aware
            created_at = created_at.replace(tzinfo=timezone.utc)

        age_days = (datetime.now(timezone.utc) - created_at).days
        recency = 1.0 / (1.0 + age_days)

        return (
            self.sem_score * sem_weight
            + self.fts_score * fts_weight
            + imp * imp_boost
            + recency * rec_boost
        )


@dataclass
class HybridSearchParams:
    """Parameters for hybrid search configuration."""

    semantic_weight: float = 0.7
    fts_weight: float = 0.3
    recency_boost: float = 0.1
    importance_boost: float = 0.2


# --- LanceDB Models ---


class MemoryBlockModel(LanceModel):
    """Schema for core memory blocks (key-value)."""

    label: str
    content: str
    chat_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ArchivalMemoryModel(LanceModel):
    """Schema for archival memories with embeddings."""

    id: str
    content: str
    vector: Vector(CONFIG.embedding_dimension)
    user_id: str
    chat_id: Optional[str] = None
    metadata: str  # JSON string
    importance: float
    created_at: datetime
    updated_at: datetime
    accessed_at: Optional[datetime] = None
    access_count: int = 0


# --- Main Store Class ---


class LanceDBMemoryStore:
    """
    LanceDB-based memory store with vector and full-text search.

    This store manages two types of memory:
    1. Memory Blocks: Key-value pairs scoped by user/chat (e.g., persona, system prompts)
    2. Archival Memories: Vector-embedded content with hybrid search capabilities

    The store supports:
    - Semantic search using cosine similarity on embeddings
    - Full-text search using LanceDB's native FTS index
    - Hybrid search combining multiple ranking signals
    - User/chat scoping with priority matching
    - SQL injection protection
    """

    def __init__(
        self,
        uri: str = ".suzent/data/memory",
        embedding_dim: int = CONFIG.embedding_dimension,
    ):
        self.uri: str = uri
        self.embedding_dim: int = embedding_dim
        self.db: Optional[lancedb.AsyncDatabase] = None
        self.archival_table = None
        self.blocks_table = None

    async def connect(self) -> None:
        """Initialize connection to LanceDB."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.uri)), exist_ok=True)
            self.db = await lancedb.connect_async(self.uri)
            await self._init_tables()
            logger.info(f"LanceDB connection established at {self.uri}")
        except Exception as e:
            logger.error(f"Failed to connect to LanceDB: {e}")
            raise

    async def _init_tables(self) -> None:
        """Initialize tables if they don't exist."""
        table_names = await self.db.list_tables()

        # Memory Blocks
        if "memory_blocks" not in table_names:
            self.blocks_table = await self.db.create_table(
                "memory_blocks", schema=MemoryBlockModel, exist_ok=True
            )
            logger.info("Created memory_blocks table")
        else:
            self.blocks_table = await self.db.open_table("memory_blocks")

        # Archival Memories
        if "archival_memories" not in table_names:
            self.archival_table = await self.db.create_table(
                "archival_memories", schema=ArchivalMemoryModel, exist_ok=True
            )
            logger.info("Created archival_memories table")

            try:
                await self.archival_table.create_index(
                    "content",
                    config=FTS(language="English", stem=True, remove_stop_words=True),
                )
                logger.info("Created FTS index on archival_memories.content")
            except Exception as e:
                logger.warning(f"Could not create FTS index: {e}")
        else:
            self.archival_table = await self.db.open_table("archival_memories")

        # Validate embedding dimension
        if self.archival_table:
            try:
                schema = await self.archival_table.schema()
                vector_field = schema.field("vector")
                actual_dim = vector_field.type.list_size

                if actual_dim != self.embedding_dim:
                    raise ValueError(
                        f"Embedding dimension mismatch!\n"
                        f"  Existing table: {actual_dim} dimensions\n"
                        f"  Current config: {self.embedding_dim} dimensions\n"
                        f"Solution: Delete '{self.uri}' or update CONFIG.embedding_dimension"
                    )
                logger.info(f"Validated embedding dimension: {actual_dim}D")
            except Exception as e:
                logger.warning(f"Could not validate embedding dimension: {e}")

    async def close(self) -> None:
        """Close connection (no-op for LanceDB async client)."""
        # LanceDB async client doesn't require explicit cleanup
        pass

    # --- Filter Building Helpers ---

    @staticmethod
    def _build_user_chat_filter(user_id: str, chat_id: Optional[str] = None) -> str:
        """Build common user/chat filter with SQL escaping."""
        filters = [f"user_id = '{_escape_sql(user_id)}'"]
        if chat_id:
            filters.append(f"(chat_id = '{_escape_sql(chat_id)}' OR chat_id IS NULL)")
        return " AND ".join(filters)

    # --- Scoring Helpers ---

    @staticmethod
    def _calculate_block_priority(
        row: Dict[str, Any], chat_id: Optional[str], user_id: Optional[str]
    ) -> int:
        """Calculate priority score for a memory block."""
        score = 0
        if chat_id and row.get("chat_id") == chat_id:
            score += CHAT_MATCH_BONUS
        if user_id and row.get("user_id") == user_id:
            score += USER_MATCH_BONUS
        return score

    def _score_memory_block(
        self, row: Dict[str, Any], chat_id: Optional[str], user_id: Optional[str]
    ) -> Tuple[int, datetime]:
        """Score a memory block for priority sorting (higher is better)."""
        score = self._calculate_block_priority(row, chat_id, user_id)
        return (score, row["created_at"])

    # --- Result Formatting Helpers ---

    @staticmethod
    def _format_memory_result(row: Dict[str, Any], **extra_fields) -> Dict[str, Any]:
        """Format a memory row into a standard result dict."""
        result = {
            "id": row["id"],
            "content": row["content"],
            "metadata": json.loads(row["metadata"]),
            "importance": row["importance"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "access_count": row["access_count"],
        }
        result.update(extra_fields)
        return result

    # --- Core Memory Block Operations ---

    async def get_memory_block(
        self, label: str, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> Optional[str]:
        """Get a core memory block with prioritized matching."""
        try:
            # Build filter conditions
            conditions = [f"label = '{_escape_sql(label)}'"]

            if user_id is not None:
                conditions.append(f"user_id = '{_escape_sql(user_id)}'")
            else:
                conditions.append("user_id IS NULL")

            if chat_id is not None:
                conditions.append(
                    f"(chat_id = '{_escape_sql(chat_id)}' OR chat_id IS NULL)"
                )
            else:
                conditions.append("chat_id IS NULL")

            clause = " AND ".join(conditions)
            query = self.blocks_table.query()
            results = await query.where(clause).to_arrow()

            if len(results) == 0:
                return None

            # Sort by priority: chat match > user match > recency
            rows = results.to_pylist()
            rows.sort(
                key=lambda r: self._score_memory_block(r, chat_id, user_id),
                reverse=True,
            )
            return rows[0]["content"]

        except Exception as e:
            logger.error(f"Error getting memory block: {e}")
            return None

    async def get_all_memory_blocks(
        self, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get all core memory blocks as a dictionary, with priority matching."""
        try:
            conditions = []

            if chat_id:
                conditions.append(
                    f"(chat_id = '{_escape_sql(chat_id)}' OR chat_id IS NULL)"
                )
            else:
                conditions.append("chat_id IS NULL")

            if user_id:
                conditions.append(
                    f"(user_id = '{_escape_sql(user_id)}' OR user_id IS NULL)"
                )
            else:
                conditions.append("user_id IS NULL")

            clause = " AND ".join(conditions)
            query = self.blocks_table.query()
            results = await query.where(clause).to_arrow()
            rows = results.to_pylist()

            # Group by label and pick the best match for each
            best_blocks = {}
            for row in rows:
                label = row["label"]
                score = self._calculate_block_priority(row, chat_id, user_id)

                if label not in best_blocks:
                    best_blocks[label] = (score, row)
                else:
                    cur_score, cur_row = best_blocks[label]
                    # Replace if higher score, or same score but newer
                    if score > cur_score or (
                        score == cur_score and row["created_at"] > cur_row["created_at"]
                    ):
                        best_blocks[label] = (score, row)

            return {label: row["content"] for label, (_, row) in best_blocks.items()}

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
        """Set or update a core memory block (replaces existing)."""
        try:
            # Build delete clause to remove existing block with same label/user/chat
            conditions = [f"label = '{_escape_sql(label)}'"]

            if chat_id is not None:
                conditions.append(f"chat_id = '{_escape_sql(chat_id)}'")
            else:
                conditions.append("chat_id IS NULL")

            if user_id is not None:
                conditions.append(f"user_id = '{_escape_sql(user_id)}'")
            else:
                conditions.append("user_id IS NULL")

            clause = " AND ".join(conditions)
            await self.blocks_table.delete(clause)

            # Add new block
            new_block = MemoryBlockModel(
                label=label,
                content=content,
                chat_id=chat_id,
                user_id=user_id,
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )

            await self.blocks_table.add([new_block])
            return True

        except Exception as e:
            logger.error(f"Error setting memory block: {e}")
            return False

    # --- Archival Memory Operations ---

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
        try:
            mem_id = str(uuid.uuid4())
            new_mem = ArchivalMemoryModel(
                id=mem_id,
                content=content,
                vector=embedding,
                user_id=user_id,
                chat_id=chat_id,
                metadata=json.dumps(metadata or {}),
                importance=importance,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                accessed_at=None,
                access_count=0,
            )

            await self.archival_table.add([new_mem])
            return mem_id

        except Exception as e:
            logger.error(f"Error adding memory: {e}")
            raise

    async def semantic_search(
        self,
        query_embedding: List[float],
        user_id: str,
        limit: int = 10,
        chat_id: Optional[str] = None,
        min_importance: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Pure semantic search using vector similarity."""
        try:
            where = self._build_user_chat_filter(user_id, chat_id)
            if min_importance > 0:
                where += f" AND importance >= {min_importance}"

            qb = await self.archival_table.search(
                query_embedding, vector_column_name="vector"
            )
            results = await (
                qb.distance_type("cosine").where(where).limit(limit).to_list()
            )

            formatted_results = [
                self._format_memory_result(r, similarity=1.0 - r["_distance"])
                for r in results
            ]

            try:
                await self._record_memory_accesses(formatted_results)
            except Exception as access_error:
                logger.warning(
                    f"Failed to update access counts in semantic search: {access_error}"
                )

            return formatted_results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    # --- Hybrid Search Helpers ---

    async def _perform_semantic_search_internal(
        self, query_embedding: List[float], where: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Execute semantic search query."""
        qb = await self.archival_table.search(
            query_embedding, vector_column_name="vector"
        )
        return await qb.distance_type("cosine").where(where).limit(limit).to_list()

    async def _perform_fts_search(
        self, query_text: str, where: str, limit: int
    ) -> List[Dict[str, Any]]:
        """Execute full-text search query."""
        try:
            qb = await self.archival_table.search(query_text, query_type="fts")
            results = await qb.where(where).limit(limit).to_list()
            logger.debug(
                f"FTS search for '{query_text}' returned {len(results)} results"
            )
            return results
        except Exception as e:
            logger.warning(f"FTS failed (index might be missing): {e}")
            return []

    async def fts_search(
        self,
        query_text: str,
        user_id: str,
        chat_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Public FTS-only search (no embedding API call, purely local)."""
        where = self._build_user_chat_filter(user_id, chat_id)
        return await self._perform_fts_search(query_text, where, limit)

    @staticmethod
    def _normalize_fts_scores(fts_results: List[Dict[str, Any]]) -> float:
        """Get max FTS score for normalization."""
        if not fts_results:
            return 1.0
        return max(r.get("_score", 1.0) for r in fts_results)

    @staticmethod
    def _merge_search_results(
        sem_results: List[Dict[str, Any]],
        fts_results: List[Dict[str, Any]],
        max_fts_score: float,
    ) -> Dict[str, ScoredResult]:
        """Merge semantic and FTS results into combined scored results."""
        combined = {}

        for r in sem_results:
            combined[r["id"]] = ScoredResult(
                doc=r, sem_score=1.0 - r["_distance"], fts_score=0.0
            )

        for r in fts_results:
            fts_score_normalized = (
                r.get("_score", 0.0) / max_fts_score if max_fts_score > 0 else 0.0
            )

            if r["id"] not in combined:
                combined[r["id"]] = ScoredResult(
                    doc=r, sem_score=0.0, fts_score=fts_score_normalized
                )
            else:
                combined[r["id"]].fts_score = fts_score_normalized

        return combined

    def _calculate_final_scores(
        self, combined: Dict[str, ScoredResult], params: HybridSearchParams
    ) -> List[Dict[str, Any]]:
        """Calculate final scores and format results."""
        scored_results = []

        for mid, scored in combined.items():
            final_score = scored.calculate_final_score(
                params.semantic_weight,
                params.fts_weight,
                params.importance_boost,
                params.recency_boost,
            )

            result = self._format_memory_result(scored.doc, score=final_score)
            scored_results.append(result)

        return scored_results

    async def _record_memory_accesses(self, results: List[Dict[str, Any]]) -> None:
        """Increment access counters for retrieved memories."""
        if not results:
            return

        now = _utc_now()
        for result in results:
            memory_id = result.get("id")
            if not memory_id:
                continue

            current_access_count = int(result.get("access_count", 0))
            await self.archival_table.update(
                where=f"id = '{_escape_sql(str(memory_id))}'",
                updates={
                    "access_count": current_access_count + 1,
                    "accessed_at": now,
                },
            )

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
        Hybrid search combining semantic similarity, full-text search,
        recency, and importance scoring.
        """
        try:
            params = HybridSearchParams(
                semantic_weight, fts_weight, recency_boost, importance_boost
            )

            where = self._build_user_chat_filter(user_id, chat_id)

            # Execute searches in parallel
            sem_results, fts_results = await asyncio.gather(
                self._perform_semantic_search_internal(
                    query_embedding, where, limit * 2
                ),
                self._perform_fts_search(query_text, where, limit * 2),
            )

            # Merge and score
            max_fts_score = self._normalize_fts_scores(fts_results)
            combined = self._merge_search_results(
                sem_results, fts_results, max_fts_score
            )
            scored_results = self._calculate_final_scores(combined, params)

            # Sort and limit
            scored_results.sort(key=lambda x: x["score"], reverse=True)
            final_results = scored_results[:limit]
            try:
                await self._record_memory_accesses(final_results)
            except Exception as access_error:
                logger.warning(
                    f"Failed to update access counts in hybrid search: {access_error}"
                )

            return final_results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    # --- Update/Delete Operations ---

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        embedding: Optional[List[float]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
    ) -> bool:
        """Update memory content and/or embedding."""
        try:
            vals = {"updated_at": _utc_now()}

            if content is not None:
                vals["content"] = content
            if embedding is not None:
                vals["vector"] = embedding
            if metadata is not None:
                vals["metadata"] = json.dumps(metadata)
            if importance is not None:
                vals["importance"] = importance

            await self.archival_table.update(
                where=f"id = '{_escape_sql(memory_id)}'", updates=vals
            )
            return True

        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory."""
        try:
            await self.archival_table.delete(f"id = '{_escape_sql(memory_id)}'")
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False

    async def delete_all_memories(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> bool:
        """Delete all archival memories for a user/chat."""
        try:
            clause = f"user_id = '{_escape_sql(user_id)}'"
            if chat_id:
                clause += f" AND chat_id = '{_escape_sql(chat_id)}'"

            await self.archival_table.delete(clause)
            return True
        except Exception as e:
            logger.error(f"Delete all memories failed: {e}")
            return False

    async def delete_memories_by_source_file(
        self, source_file: str, user_id: str
    ) -> bool:
        """Delete all archival memories that originated from a specific core memory file.

        Used by CoreMemoryFileIndexer to clear stale chunks before re-indexing.
        Matches on the JSON metadata field using a LIKE pattern.

        Args:
            source_file: File name (e.g., 'persona.md', 'user.md', 'MEMORY.md')
            user_id: User scope
        """
        try:
            safe_user = _escape_sql(user_id)
            # Escape double-quotes for SQL LIKE pattern (they appear in JSON)
            safe_file = source_file.replace("'", "").replace('"', '\\"')
            clause = (
                f"user_id = '{safe_user}'"
                f' AND metadata LIKE \'%"source_file": "{safe_file}"%\''
            )
            await self.archival_table.delete(clause)
            logger.debug(f"Deleted archival memories for source_file={source_file}")
            return True
        except Exception as e:
            logger.error(f"delete_memories_by_source_file failed: {e}")
            return False

    async def delete_memories_by_source_date(self, date: str, user_id: str) -> bool:
        """Delete archival memories for a given archive date (YYYY-MM-DD).

        Covers both old entries (source_date field, no source_file) and new
        entries (source_file = YYYY-MM-DD.md) so re-indexing archive files
        does not produce duplicates regardless of how they were first written.

        Args:
            date: Date string in YYYY-MM-DD format
            user_id: User scope
        """
        try:
            safe_user = _escape_sql(user_id)
            safe_date = date.replace("'", "")
            safe_file = f"{safe_date}.md".replace('"', '\\"')
            clause = (
                f"user_id = '{safe_user}'"
                f' AND (metadata LIKE \'%"source_date": "{safe_date}"%\''
                f'   OR metadata LIKE \'%"source_file": "{safe_file}"%\')'
            )
            await self.archival_table.delete(clause)
            logger.debug(f"Deleted archival memories for source_date={date}")
            return True
        except Exception as e:
            logger.error(f"delete_memories_by_source_date failed: {e}")
            return False

    async def delete_all_memory_blocks(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> bool:
        """Delete all memory blocks for a user/chat."""
        try:
            conditions = [f"(user_id = '{_escape_sql(user_id)}' OR user_id IS NULL)"]
            if chat_id:
                conditions.append(
                    f"(chat_id = '{_escape_sql(chat_id)}' OR chat_id IS NULL)"
                )

            clause = " AND ".join(conditions)
            await self.blocks_table.delete(clause)
            return True
        except Exception as e:
            logger.error(f"Delete all memory blocks failed: {e}")
            return False

    # --- Query Operations ---

    async def get_memory_count(
        self, user_id: str, chat_id: Optional[str] = None
    ) -> int:
        """Get total number of memories for a user."""
        try:
            clause = f"user_id = '{_escape_sql(user_id)}'"
            if chat_id:
                clause += f" AND chat_id = '{_escape_sql(chat_id)}'"

            return await self.archival_table.count_rows(clause)
        except Exception as e:
            logger.error(f"Get memory count failed: {e}")
            return 0

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
        try:
            clause = f"user_id = '{_escape_sql(user_id)}'"
            if chat_id:
                clause += f" AND chat_id = '{_escape_sql(chat_id)}'"

            query = self.archival_table.query()
            res = await query.where(clause).limit(limit + offset).to_arrow()
            rows = res.to_pylist()

            # Sort by specified column
            reverse = order_desc
            if order_by in ["created_at", "updated_at", "accessed_at"]:
                rows.sort(
                    key=lambda x: x.get(order_by) or datetime.min, reverse=reverse
                )
            elif order_by in ["importance", "access_count"]:
                rows.sort(key=lambda x: x.get(order_by, 0), reverse=reverse)

            # Apply offset and limit
            final = rows[offset : offset + limit]

            return [self._format_memory_result(r) for r in final]

        except Exception as e:
            logger.error(f"List memories failed: {e}")
            return []

    # --- Statistics Operations ---

    @staticmethod
    def _empty_stats() -> Dict[str, Any]:
        """Return empty statistics structure."""
        return {
            "total_memories": 0,
            "avg_importance": 0.0,
            "max_importance": 0.0,
            "min_importance": 0.0,
            "total_accesses": 0,
            "avg_access_count": 0.0,
            "importance_distribution": {"high": 0, "medium": 0, "low": 0},
            "utilized_memories": 0,
            "utilization_rate": 0.0,
            "recently_accessed_memories_7d": 0,
            "recent_activity_rate_7d": 0.0,
            "cold_memories": 0,
            "cold_memory_ratio": 0.0,
            "access_distribution": {"unaccessed": 0, "light": 0, "engaged": 0},
        }

    @staticmethod
    def _categorize_importance(importances: List[float]) -> Dict[str, int]:
        """Categorize importance scores into high/medium/low."""
        categories = [
            "high" if imp >= 0.8 else "medium" if imp >= 0.5 else "low"
            for imp in importances
        ]
        counts = Counter(categories)
        return {
            "high": counts.get("high", 0),
            "medium": counts.get("medium", 0),
            "low": counts.get("low", 0),
        }

    @staticmethod
    def _categorize_access(access_counts: List[int]) -> Dict[str, int]:
        """Group memories by access intensity."""
        categories = [
            "unaccessed" if count <= 0 else "light" if count <= 2 else "engaged"
            for count in access_counts
        ]
        counts = Counter(categories)
        return {
            "unaccessed": counts.get("unaccessed", 0),
            "light": counts.get("light", 0),
            "engaged": counts.get("engaged", 0),
        }

    @staticmethod
    def _is_recent_access(accessed_at: Optional[datetime], now: datetime) -> bool:
        """Check if memory has been accessed in the last 7 days."""
        if accessed_at is None:
            return False

        if accessed_at.tzinfo is None:
            accessed_at = accessed_at.replace(tzinfo=timezone.utc)

        return (now - accessed_at).days < 7

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get memory statistics for a user."""
        try:
            query = self.archival_table.query()
            clause = f"user_id = '{_escape_sql(user_id)}'"
            results = await query.where(clause).to_arrow()
            rows = results.to_pylist()

            if not rows:
                return self._empty_stats()

            total_memories = len(rows)
            now = datetime.now(timezone.utc)
            importances = [r["importance"] for r in rows]
            access_counts = [r["access_count"] for r in rows]
            utilized_memories = sum(1 for count in access_counts if count > 0)
            cold_memories = total_memories - utilized_memories
            recently_accessed_memories_7d = sum(
                1 for row in rows if self._is_recent_access(row.get("accessed_at"), now)
            )

            return {
                "total_memories": total_memories,
                "avg_importance": statistics.mean(importances),
                "max_importance": max(importances),
                "min_importance": min(importances),
                "total_accesses": sum(access_counts),
                "avg_access_count": statistics.mean(access_counts)
                if access_counts
                else 0.0,
                "importance_distribution": self._categorize_importance(importances),
                "utilized_memories": utilized_memories,
                "utilization_rate": utilized_memories / total_memories,
                "recently_accessed_memories_7d": recently_accessed_memories_7d,
                "recent_activity_rate_7d": recently_accessed_memories_7d
                / total_memories,
                "cold_memories": cold_memories,
                "cold_memory_ratio": cold_memories / total_memories,
                "access_distribution": self._categorize_access(access_counts),
            }

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return self._empty_stats()
