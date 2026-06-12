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

import asyncio
import json
import re
from pathlib import Path
from typing import List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

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
    """Watches persona.md, user.md, MEMORY.md, and archive/*.md for changes
    and keeps their embeddings current in the LanceDB archival_memories table.

    Change detection uses mtime (last-modified timestamp) so unchanged files
    cost nothing.  On a detected change the old chunks for that file are deleted
    and new ones are embedded and inserted.

    mtime state is persisted to .index_state.json inside the memory directory
    so that restarts do not trigger unnecessary re-indexing.

    Designed to run as a background asyncio loop (see lifecycle.py).
    """

    INDEX_STATE_FILENAME = ".index_state.json"

    # Map from block label → filename as stored in LanceDB metadata
    CORE_FILES: dict = {
        "persona": "persona.md",
        "user": "user.md",
        "facts": "MEMORY.md",
    }

    def __init__(self) -> None:
        # path_str → last known mtime (float)
        self._mtimes: dict = {}
        self._state_path: Optional[Path] = None
        # Serializes all index mutations (per-turn reindex_file_now, the background
        # watcher's check_and_update, and the dream's reconcile).
        self._lock = asyncio.Lock()

    def _load_state(self, markdown_store) -> None:
        """Load persisted mtime state from disk (called once on first check).

        If the state file does not exist, pre-populate mtimes from all existing
        files so that the first run after this change skips re-indexing entirely.
        """
        import json as _json

        self._state_path = markdown_store.base_dir / self.INDEX_STATE_FILENAME
        if self._state_path.exists():
            try:
                self._mtimes = _json.loads(self._state_path.read_text(encoding="utf-8"))
                logger.debug(f"Loaded index state: {len(self._mtimes)} entries")
            except Exception as e:
                logger.warning(f"Failed to load index state, starting fresh: {e}")
                self._mtimes = {}
        else:
            # First run — snapshot current mtimes without indexing anything.
            for label, filename in self.CORE_FILES.items():
                path = (
                    markdown_store.memory_file_path
                    if label == "facts"
                    else markdown_store._block_path(label)
                )
                if path.exists():
                    self._mtimes[str(path)] = path.stat().st_mtime
            for archive_path in markdown_store.archive_dir.glob("????-??-??.md"):
                self._mtimes[str(archive_path)] = archive_path.stat().st_mtime
            self._save_state()
            logger.info(
                f"Initialized index state with {len(self._mtimes)} existing files (no reindex)"
            )

    def _save_state(self) -> None:
        """Persist mtime state to disk."""
        if self._state_path is None:
            return
        try:
            import json as _json

            self._state_path.write_text(
                _json.dumps(self._mtimes, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logger.warning(f"Failed to save index state: {e}")

    async def check_and_update(
        self,
        markdown_store,
        lancedb_store,
        embedding_gen,
        user_id: str,
    ) -> dict:
        """Locked wrapper — serializes against per-turn reindex and the dream reconcile."""
        async with self._lock:
            return await self._check_and_update_impl(
                markdown_store, lancedb_store, embedding_gen, user_id
            )

    async def _check_and_update_impl(
        self,
        markdown_store,
        lancedb_store,
        embedding_gen,
        user_id: str,
    ) -> dict:
        """Check all core memory files and archive logs for changes and re-index changed ones.

        Returns:
            Dict with stats: files_checked, files_updated, chunks_indexed, errors
        """
        # Load persisted state on first call
        if self._state_path is None:
            self._load_state(markdown_store)

        stats = {
            "files_checked": 0,
            "files_updated": 0,
            "chunks_indexed": 0,
            "errors": 0,
        }

        # Build list of (path, label, filename) for all files to check
        entries: list[tuple[Path, str, str]] = []

        for label, filename in self.CORE_FILES.items():
            if label == "facts":
                path = markdown_store.memory_file_path
            else:
                path = markdown_store._block_path(label)
            entries.append((path, label, filename))

        # Archive daily logs
        for archive_path in sorted(markdown_store.archive_dir.glob("????-??-??.md")):
            entries.append((archive_path, "archive", archive_path.name))

        # Notebook vault pages (recursive; root-relative source_file key)
        for page in markdown_store.list_notebook_pages():
            entries.append((page, "notebook", markdown_store.notebook_rel(page)))

        # Watermark (archives ≤ W are consolidated → dropped) + tombstones (skip deleted facts)
        watermark = markdown_store.read_watermark()
        tombstones = markdown_store.read_tombstones()

        state_dirty = False

        for path, label, filename in entries:
            stats["files_checked"] += 1

            if not path.exists():
                continue

            path_key = str(path)

            # Watermark-aware archives: a log already folded into the vault (date ≤ W)
            # must NOT remain in the search index — drop it once.
            if label == "archive" and watermark:
                date = filename.removesuffix(".md")
                if date <= watermark:
                    if path_key in self._mtimes:
                        await lancedb_store.delete_memories_by_source_date(date, user_id)
                        del self._mtimes[path_key]
                        state_dirty = True
                    continue

            mtime = path.stat().st_mtime
            if self._mtimes.get(path_key) == mtime:
                continue  # File unchanged — nothing to do

            try:
                content = path.read_text(encoding="utf-8").strip()
                if not content:
                    self._mtimes[path_key] = mtime
                    state_dirty = True
                    continue

                n = await self._reindex_file(
                    label=label,
                    filename=filename,
                    content=content,
                    lancedb_store=lancedb_store,
                    embedding_gen=embedding_gen,
                    user_id=user_id,
                    tombstones=tombstones,
                )
                self._mtimes[path_key] = mtime
                state_dirty = True
                stats["files_updated"] += 1
                stats["chunks_indexed"] += n
                logger.info(f"Re-indexed {filename}: {n} rows")

            except Exception as e:
                stats["errors"] += 1
                logger.error(f"Failed to re-index {filename}: {e}")

        if state_dirty:
            self._save_state()

        return stats

    async def reindex_file_now(
        self,
        markdown_store,
        lancedb_store,
        embedding_gen,
        user_id: str,
        label: str,
        filename: str,
    ) -> int:
        """Immediately (re)index ONE file: delete its existing rows, re-embed its
        current content, and record the new mtime so the background watcher won't
        redundantly re-index it. Delete-then-add makes this idempotent and race-free
        with the watcher. Used by the per-turn write path (label="archive").
        """
        async with self._lock:
            if self._state_path is None:
                self._load_state(markdown_store)

            if label == "archive":
                path = markdown_store.archive_dir / filename
            elif label == "notebook":
                path = markdown_store.notebook_dir / filename
            else:
                path = markdown_store._block_path(label)

            if not path.exists():
                return 0

            content = path.read_text(encoding="utf-8").strip()
            if not content:
                self._mtimes[str(path)] = path.stat().st_mtime
                self._save_state()
                return 0

            n = await self._reindex_file(
                label=label,
                filename=filename,
                content=content,
                lancedb_store=lancedb_store,
                embedding_gen=embedding_gen,
                user_id=user_id,
                tombstones=markdown_store.read_tombstones(),
            )
            # Record post-write mtime so the watcher treats this file as handled.
            self._mtimes[str(path)] = path.stat().st_mtime
            self._save_state()
            return n

    async def clear_and_full_reindex(
        self,
        markdown_store,
        lancedb_store,
        embedding_gen,
        user_id: str,
    ) -> dict:
        """Wipe the user's LanceDB rows and rebuild the index from files (core +
        notebook + post-watermark archives). Used by the reindex route / migration.
        """
        async with self._lock:
            await lancedb_store.delete_all_memories(user_id=user_id)
            self._mtimes = {}
            if self._state_path is None:
                self._state_path = markdown_store.base_dir / self.INDEX_STATE_FILENAME
            self._save_state()
            return await self._check_and_update_impl(
                markdown_store, lancedb_store, embedding_gen, user_id
            )

    async def _reindex_file(
        self,
        label: str,
        filename: str,
        content: str,
        lancedb_store,
        embedding_gen,
        user_id: str,
        tombstones: Optional[set] = None,
    ) -> int:
        """Delete stale rows and re-embed the content of one file. Idempotent.

        Diary logs are indexed one row per fact (§A); notebook pages and core files
        one row per paragraph chunk. Tombstoned diary facts are skipped so user
        deletions never resurrect. Returns the number of rows indexed.
        """
        tombstones = tombstones or set()

        # 1. Build the rows to index: (text, metadata, importance). Importance is a
        #    constant — ranking is relevance + recency, not a tuned lever.
        if label == "archive":
            rows = [
                (
                    fact["content"],
                    {
                        "source_type": "archive_log",
                        "source_file": filename,
                        "category": fact["category"],
                        "tags": fact["tags"],
                    },
                    0.5,
                )
                for fact in self._parse_archive_facts(content)
                if fact["content"]
                and " ".join(fact["content"].lower().split()) not in tombstones
            ]
        else:
            source_type = "notebook" if label == "notebook" else "core_file"
            tags = (
                ["notebook", filename]
                if label == "notebook"
                else ["core_memory", label, filename]
            )
            rows = [
                (
                    chunk,
                    {
                        "source_type": source_type,
                        "source_file": filename,
                        "chunk_index": i,
                        "label": label,
                        "category": source_type,
                        "tags": tags,
                    },
                    0.5,
                )
                for i, chunk in enumerate(self._chunk_by_paragraphs(content))
                if chunk.strip()
            ]

        # 2. Embed ALL rows BEFORE mutating the index. embedding_gen.generate() raises
        #    on failure (e.g. embedding backend unreachable) — letting it propagate here
        #    leaves the existing index untouched and the file gets retried next pass,
        #    instead of deleting rows and replacing them with poisoned zero vectors.
        embeddings = [await embedding_gen.generate(text) for text, _, _ in rows]

        # 3. Replace: clear this file's old rows, then add the freshly-embedded ones.
        #    Reached only after every embedding succeeded. Archive logs may also carry
        #    legacy source_date metadata, so use the broader date-based delete for them.
        if label == "archive":
            await lancedb_store.delete_memories_by_source_date(
                filename.removesuffix(".md"), user_id
            )
        else:
            await lancedb_store.delete_memories_by_source_file(filename, user_id)

        indexed = 0
        for (text, metadata, importance), embedding in zip(rows, embeddings):
            await lancedb_store.add_memory(
                content=text,
                embedding=embedding,
                user_id=user_id,
                chat_id=None,
                metadata=metadata,
                importance=importance,
            )
            indexed += 1

        return indexed

    @staticmethod
    def _parse_archive_facts(content: str) -> List[dict]:
        """Parse daily-log fact lines ``- [category] content `tags``` into dicts.

        Non-fact lines (file/section headers, blanks) are ignored.
        """
        facts: List[dict] = []
        for raw in content.splitlines():
            m = re.match(r"^-\s*\[([^\]]+)\]\s*(.*)$", raw.strip())
            if not m:
                continue
            category = m.group(1).strip()
            rest = m.group(2).strip()
            tags: List[str] = []
            tag_m = re.search(r"`([^`]*)`\s*$", rest)
            if tag_m:
                tags = tag_m.group(1).split()
                rest = rest[: tag_m.start()].strip()
            if rest:
                facts.append({"content": rest, "category": category, "tags": tags})
        return facts

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
