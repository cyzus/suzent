"""
Markdown-to-LanceDB indexer.

Rebuilds the LanceDB search index from markdown memory files.
This ensures that if LanceDB data is lost or corrupted, the markdown
source of truth can fully restore the search index.

Also provides:
- TranscriptIndexer: chunks JSONL session transcripts into LanceDB
- CoreMemoryFileIndexer: watches persona.md / user.md / MEMORY.md for
  changes and keeps their embeddings in LanceDB up to date (Phase 2)
"""

import json
import re
from pathlib import Path
from typing import List

from suzent.logger import get_logger

logger = get_logger(__name__)

# Parsing constants
DAILY_LOG_ENTRY_PATTERN = re.compile(r"^## (\d{2}:\d{2}) - Chat: (\w+)", re.MULTILINE)
FACT_LINE_PATTERN = re.compile(
    r"^- \*\*\[(\w+)\]\*\* (.+?) \(importance: ([\d.]+)\)", re.MULTILINE
)
TAGS_PATTERN = re.compile(r"^\s+- Tags: (.+)$", re.MULTILINE)


class MarkdownIndexer:
    """
    Rebuilds LanceDB archival_memories from markdown memory files.

    Parses daily log files (YYYY-MM-DD.md) and re-indexes their content
    into the LanceDB vector store, generating embeddings for each fact.
    """

    async def reindex_from_markdown(
        self,
        markdown_store,
        lancedb_store,
        embedding_gen,
        user_id: str,
        clear_existing: bool = False,
    ) -> dict:
        """
        Parse all markdown memory files and rebuild the LanceDB index.

        Args:
            markdown_store: MarkdownMemoryStore instance
            lancedb_store: LanceDBMemoryStore instance
            embedding_gen: EmbeddingGenerator instance
            user_id: User ID to scope the memories
            clear_existing: If True, delete existing memories before re-indexing

        Returns:
            Dict with stats: total_files, total_facts, indexed, skipped, errors
        """
        stats = {
            "total_files": 0,
            "total_facts": 0,
            "indexed": 0,
            "skipped": 0,
            "errors": 0,
        }

        try:
            # Optionally clear existing archival memories
            if clear_existing:
                await lancedb_store.delete_all_memories(user_id=user_id)
                logger.info(f"Cleared existing memories for user {user_id}")

            # List all daily log files
            dates = await markdown_store.list_daily_logs()
            stats["total_files"] = len(dates)

            if not dates:
                logger.info("No daily log files found for re-indexing")
                return stats

            logger.info(f"Re-indexing {len(dates)} daily log files")

            for date in dates:
                try:
                    content = await markdown_store.read_daily_log(date)
                    if not content:
                        continue

                    facts = self._parse_daily_log(content, date)
                    stats["total_facts"] += len(facts)

                    for fact in facts:
                        try:
                            embedding = await embedding_gen.generate(fact["content"])
                            await lancedb_store.add_memory(
                                content=fact["content"],
                                embedding=embedding,
                                user_id=user_id,
                                chat_id=None,  # User-level
                                metadata=fact["metadata"],
                                importance=fact["importance"],
                            )
                            stats["indexed"] += 1
                        except Exception as e:
                            logger.warning(f"Failed to index fact from {date}: {e}")
                            stats["errors"] += 1

                except Exception as e:
                    logger.error(f"Failed to parse daily log {date}: {e}")
                    stats["errors"] += 1

            logger.info(
                f"Re-indexing complete: {stats['indexed']} indexed, "
                f"{stats['errors']} errors from {stats['total_facts']} facts"
            )

        except Exception as e:
            logger.error(f"Re-indexing failed: {e}")
            stats["errors"] += 1

        return stats

    def _parse_daily_log(self, content: str, date: str) -> List[dict]:
        """
        Parse a daily log markdown file into structured facts.

        Args:
            content: Markdown file content
            date: Date string (YYYY-MM-DD)

        Returns:
            List of fact dicts with content, importance, metadata
        """
        facts = []
        current_chat_id = None
        current_time = None

        lines = content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i]

            # Match section header: ## HH:MM - Chat: xxxxxxxx
            header_match = DAILY_LOG_ENTRY_PATTERN.match(line)
            if header_match:
                current_time = header_match.group(1)
                current_chat_id = header_match.group(2)
                i += 1
                continue

            # Match fact line: - **[category]** content (importance: 0.8)
            fact_match = FACT_LINE_PATTERN.match(line)
            if fact_match:
                category = fact_match.group(1)
                fact_content = fact_match.group(2)
                importance = float(fact_match.group(3))

                # Look ahead for tags and context
                tags = []
                context = {}
                j = i + 1
                while j < len(lines) and lines[j].startswith("  "):
                    sub_line = lines[j].strip()
                    if sub_line.startswith("- Tags:"):
                        tags = [
                            t.strip() for t in sub_line[len("- Tags:") :].split(",")
                        ]
                    elif sub_line.startswith("- Context:"):
                        context["user_intent"] = sub_line[len("- Context:") :].strip()
                    elif sub_line.startswith("- Outcome:"):
                        context["outcome"] = sub_line[len("- Outcome:") :].strip()
                    j += 1

                facts.append(
                    {
                        "content": fact_content,
                        "importance": importance,
                        "metadata": {
                            "category": category,
                            "tags": tags,
                            "source_chat_id": current_chat_id,
                            "source_date": date,
                            "source_time": current_time,
                            "conversation_context": context if context else None,
                        },
                    }
                )

                i = j
                continue

            i += 1

        return facts


# ---------------------------------------------------------------------------
# Transcript Indexer (Phase 5)
# ---------------------------------------------------------------------------

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 400  # ~400 tokens per chunk
DEFAULT_CHUNK_OVERLAP = 80  # 80 token overlap between chunks


class TranscriptIndexer:
    """
    Chunks JSONL session transcripts and embeds them into LanceDB.

    Each transcript turn is concatenated into a running text, then split
    into overlapping chunks (~400 tokens, 80 overlap). Each chunk is
    stored as an archival memory tagged with source session and line info.

    Opt-in via config: transcript_indexing_enabled = True
    """

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    async def index_transcript(
        self,
        transcript_path: Path,
        session_id: str,
        lancedb_store,
        embedding_gen,
        user_id: str,
    ) -> dict:
        """
        Read a JSONL transcript and index its content into LanceDB.

        Args:
            transcript_path: Path to the .jsonl file
            session_id: Session/chat ID
            lancedb_store: LanceDBMemoryStore instance
            embedding_gen: EmbeddingGenerator instance
            user_id: User scope

        Returns:
            Dict with stats: total_turns, total_chunks, indexed, errors
        """
        stats = {
            "total_turns": 0,
            "total_chunks": 0,
            "indexed": 0,
            "errors": 0,
        }

        if not transcript_path.exists():
            logger.debug(f"Transcript not found: {transcript_path}")
            return stats

        try:
            # Read all turns
            turns = []
            for line in transcript_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    turns.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            stats["total_turns"] = len(turns)
            if not turns:
                return stats

            # Build a running text from turns with line markers
            segments = []
            for idx, turn in enumerate(turns):
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
                ts = turn.get("ts", "")
                segments.append(f"[L{idx}|{role}|{ts}] {content}")

            full_text = "\n".join(segments)

            # Chunk with overlap (approximate token = ~4 chars)
            chunks = self._chunk_text(full_text)
            stats["total_chunks"] = len(chunks)

            # Embed and store each chunk
            for i, chunk in enumerate(chunks):
                try:
                    embedding = await embedding_gen.generate(chunk["text"])
                    await lancedb_store.add_memory(
                        content=chunk["text"],
                        embedding=embedding,
                        user_id=user_id,
                        chat_id=None,  # User-level for cross-session search
                        metadata={
                            "source_type": "transcript",
                            "source_session_id": session_id,
                            "chunk_index": i,
                            "start_line": chunk["start_line"],
                            "end_line": chunk["end_line"],
                            "category": "transcript",
                            "tags": ["transcript", session_id[:8]],
                        },
                        importance=0.3,  # Transcripts are lower importance than extracted facts
                    )
                    stats["indexed"] += 1
                except Exception as e:
                    logger.warning(f"Failed to index transcript chunk {i}: {e}")
                    stats["errors"] += 1

            logger.info(
                f"Transcript indexing for {session_id}: "
                f"{stats['indexed']} chunks from {stats['total_turns']} turns"
            )

        except Exception as e:
            logger.error(f"Transcript indexing failed for {session_id}: {e}")
            stats["errors"] += 1

        return stats

    def _chunk_text(self, text: str) -> List[dict]:
        """
        Split text into overlapping chunks.

        Each chunk is ~chunk_size words with chunk_overlap word overlap.
        Returns list of dicts with text, start_line, end_line.
        """
        words = text.split()
        if not words:
            return []

        chunks = []
        step = max(1, self.chunk_size - self.chunk_overlap)
        i = 0

        while i < len(words):
            chunk_words = words[i : i + self.chunk_size]
            chunk_text = " ".join(chunk_words)

            # Extract line markers [L{n}|...] to track start/end lines
            start_line = self._extract_line_num(chunk_words[0]) if chunk_words else 0
            end_line = self._extract_line_num(chunk_words[-1]) if chunk_words else 0

            chunks.append(
                {
                    "text": chunk_text,
                    "start_line": start_line,
                    "end_line": end_line,
                }
            )

            i += step

        return chunks

    @staticmethod
    def _extract_line_num(word: str) -> int:
        """Extract line number from [L{n}|...] marker, or return 0."""
        match = re.match(r"\[L(\d+)\|", word)
        if match:
            return int(match.group(1))
        return 0


# ---------------------------------------------------------------------------
# Core Memory File Indexer (Phase 2)
# ---------------------------------------------------------------------------

# Max chars per chunk for paragraph-based splitting of core memory files.
# Core files are small, so we set a generous limit to keep context coherent.
CORE_FILE_MAX_CHUNK_CHARS = 1200


class CoreMemoryFileIndexer:
    """Watches persona.md, user.md, and MEMORY.md for changes and keeps their
    embeddings current in the LanceDB archival_memories table.

    Change detection uses mtime (last-modified timestamp) so unchanged files
    cost nothing.  On a detected change the old chunks for that file are deleted
    and new ones are embedded and inserted.

    Designed to run as a background asyncio loop (see lifecycle.py).
    """

    # Map from block label → filename as stored in LanceDB metadata
    CORE_FILES: dict = {
        "persona": "persona.md",
        "user": "user.md",
        "facts": "MEMORY.md",
    }

    def __init__(self) -> None:
        # path_str → last known mtime (float)
        self._mtimes: dict = {}

    async def check_and_update(
        self,
        markdown_store,
        lancedb_store,
        embedding_gen,
        user_id: str,
    ) -> dict:
        """Check all core memory files for changes and re-index those that changed.

        Args:
            markdown_store: MarkdownMemoryStore instance
            lancedb_store: LanceDBMemoryStore instance
            embedding_gen: EmbeddingGenerator instance
            user_id: User scope for the archival memories

        Returns:
            Dict with stats: files_checked, files_updated, chunks_indexed, errors
        """
        stats = {
            "files_checked": 0,
            "files_updated": 0,
            "chunks_indexed": 0,
            "errors": 0,
        }

        for label, filename in self.CORE_FILES.items():
            stats["files_checked"] += 1

            # Resolve physical path
            if label == "facts":
                path = markdown_store.memory_file_path
            else:
                path = markdown_store._block_path(label)

            if not path.exists():
                continue

            mtime = path.stat().st_mtime
            path_key = str(path)

            if self._mtimes.get(path_key) == mtime:
                continue  # File unchanged — nothing to do

            try:
                content = path.read_text(encoding="utf-8").strip()
                if not content:
                    self._mtimes[path_key] = mtime
                    continue

                n = await self._reindex_file(
                    label=label,
                    filename=filename,
                    content=content,
                    lancedb_store=lancedb_store,
                    embedding_gen=embedding_gen,
                    user_id=user_id,
                )
                self._mtimes[path_key] = mtime
                stats["files_updated"] += 1
                stats["chunks_indexed"] += n
                logger.info(f"Re-indexed {filename}: {n} chunks")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Failed to re-index {filename}: {e}")

        return stats

    async def _reindex_file(
        self,
        label: str,
        filename: str,
        content: str,
        lancedb_store,
        embedding_gen,
        user_id: str,
    ) -> int:
        """Delete stale chunks and re-embed the full content of one file.

        Returns the number of chunks indexed.
        """
        # 1. Remove existing entries for this file
        await lancedb_store.delete_memories_by_source_file(filename, user_id)

        # 2. Chunk the file content
        chunks = self._chunk_by_paragraphs(content)

        # 3. Embed and store each chunk
        indexed = 0
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            try:
                embedding = await embedding_gen.generate(chunk)
                await lancedb_store.add_memory(
                    content=chunk,
                    embedding=embedding,
                    user_id=user_id,
                    chat_id=None,
                    metadata={
                        "source_type": "core_file",
                        "source_file": filename,
                        "chunk_index": i,
                        "label": label,
                        "category": "core",
                        "tags": ["core_memory", label, filename],
                    },
                    importance=0.75,  # Core memory files are high-importance context
                )
                indexed += 1
            except Exception as e:
                logger.warning(f"Failed to embed chunk {i} of {filename}: {e}")

        return indexed

    @staticmethod
    def _chunk_by_paragraphs(
        content: str,
        max_chars: int = CORE_FILE_MAX_CHUNK_CHARS,
    ) -> List[str]:
        """Split *content* on double-newlines; merge short paragraphs up to *max_chars*.

        This keeps semantically related lines together while preventing any
        single chunk from becoming too large to embed efficiently.
        """
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]

        chunks: List[str] = []
        current_parts: List[str] = []
        current_len = 0

        for para in paragraphs:
            if current_len + len(para) > max_chars and current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_len = 0
            current_parts.append(para)
            current_len += len(para) + 2  # +2 for "\n\n"

        if current_parts:
            chunks.append("\n\n".join(current_parts))

        return chunks if chunks else [content]
