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
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)


def _owned_by_file(row: dict) -> bool:
    """Whether a stored row is maintained by the markdown file it came from.

    `source_file` is what makes a row reindexable: `_reindex_file` is delete-then-add
    keyed on it. A row without one is a pre-June direct insert that no file owns, and
    treating it as the indexed form of a log line is how an exported legacy fact ends
    up deleted with nothing put back.
    """
    metadata = row.get("metadata")
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata or "{}")
        except Exception:
            return False
    return bool((metadata or {}).get("source_file"))


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
            for line in transcript_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
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

# Importance floor for a claim a person verified themselves. Below 1.0 so a verified
# claim that is *also* heavily confirmed can still outrank a verified one-off, and so
# the value stays a floor rather than a ceiling everything piles up against.
HUMAN_VERIFIED_FLOOR = 0.9


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
    # Bumped when the shape or the key scheme of the state file changes; older
    # payloads are discarded on load rather than migrated.
    STATE_VERSION = 2

    # Map from block label → filename as stored in LanceDB metadata
    CORE_FILES: dict = {
        "persona": "persona.md",
        "user": "user.md",
        "facts": "MEMORY.md",
    }

    def __init__(self) -> None:
        # path_str → last known mtime (float)
        self._mtimes: dict = {}
        # Archive files already dropped from the index for being at or below the
        # watermark. Tracked separately from `_mtimes` because the drop must happen
        # even for a file this indexer has no memory of ever having indexed.
        self._swept: set = set()
        self._state_path: Optional[Path] = None
        # Serializes all index mutations (per-turn reindex_file_now, the background
        # watcher's check_and_update, and the dream's reconcile).
        self._lock = asyncio.Lock()

    @staticmethod
    def _state_key(label: str, filename: str) -> str:
        """Portable identity for a tracked file: ``label:filename``.

        Deliberately not the absolute path. Path-keyed state travels with a synced
        vault and survives a moved base dir, so entries from another machine sit in
        the file forever; any tracked file whose stale recorded mtime happens to
        match is then skipped for good and never makes it into the index. The
        (label, filename) pair is already the file's identity everywhere else —
        it is what LanceDB deletion is keyed on.
        """
        return f"{label}:{filename}"

    def _load_state(self, markdown_store) -> None:
        """Load persisted mtime state from disk (called once on first check).

        If the state file does not exist, pre-populate mtimes from all existing
        files so that the first run after this change skips re-indexing entirely.

        STATE_VERSION 1 state is keyed by absolute path and cannot be trusted (see
        _state_key), so it is discarded rather than migrated. That costs one full
        reindex, which is the point: the files it was wrongly skipping are exactly
        the ones missing from the index.
        """
        import json as _json

        self._state_path = markdown_store.base_dir / self.INDEX_STATE_FILENAME
        if self._state_path.exists():
            try:
                payload = _json.loads(self._state_path.read_text(encoding="utf-8"))
                if (
                    isinstance(payload, dict)
                    and payload.get("version") == self.STATE_VERSION
                ):
                    mtimes = payload.get("mtimes")
                    self._mtimes = mtimes if isinstance(mtimes, dict) else {}
                    swept = payload.get("swept")
                    self._swept = set(swept) if isinstance(swept, list) else set()
                    logger.debug(f"Loaded index state: {len(self._mtimes)} entries")
                else:
                    self._mtimes = {}
                    self._swept = set()
                    logger.info(
                        "Index state is path-keyed (pre-v%s); discarding it so every "
                        "tracked file is re-indexed once." % self.STATE_VERSION
                    )
            except Exception as e:
                logger.warning(f"Failed to load index state, starting fresh: {e}")
                self._mtimes = {}
                self._swept = set()
        else:
            # First run — snapshot current mtimes without indexing anything.
            for label, filename in self.CORE_FILES.items():
                path = (
                    markdown_store.memory_file_path
                    if label == "facts"
                    else markdown_store._block_path(label)
                )
                if path.exists():
                    self._mtimes[self._state_key(label, filename)] = (
                        path.stat().st_mtime
                    )
            for archive_path in markdown_store.archive_dir.glob("????-??-??.md"):
                self._mtimes[self._state_key("archive", archive_path.name)] = (
                    archive_path.stat().st_mtime
                )
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
                _json.dumps(
                    {
                        "version": self.STATE_VERSION,
                        "mtimes": self._mtimes,
                        "swept": sorted(self._swept),
                    },
                    indent=2,
                ),
                encoding="utf-8",
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

            path_key = self._state_key(label, filename)

            # Watermark-aware archives: a log already folded into the vault (date ≤ W)
            # must NOT remain in the search index — drop it once.
            if label == "archive" and watermark:
                date = filename.removesuffix(".md")
                if date <= watermark:
                    # Sweep once per log, whether or not *this* indexer remembers
                    # having written it: rows from an older chunking scheme, or from
                    # before a state reset, are otherwise stranded forever.
                    if path_key not in self._swept:
                        await lancedb_store.delete_memories_by_source_date(
                            date, user_id
                        )
                        self._mtimes.pop(path_key, None)
                        self._swept.add(path_key)
                        state_dirty = True
                    continue

            mtime, birthtime = self.file_times(path)
            if mtime is None or self._mtimes.get(path_key) == mtime:
                continue  # File unchanged (or unreadable) — nothing to do

            try:
                content = path.read_text(encoding="utf-8", errors="replace").strip()
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
                    mtime=mtime,
                    birthtime=birthtime,
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

            file_mtime, file_birthtime = self.file_times(path)
            content = path.read_text(encoding="utf-8", errors="replace").strip()
            if not content:
                self._mtimes[self._state_key(label, filename)] = path.stat().st_mtime
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
                mtime=file_mtime,
                birthtime=file_birthtime,
            )
            # Record post-write mtime so the watcher treats this file as handled.
            self._mtimes[self._state_key(label, filename)] = path.stat().st_mtime
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
            self._swept = set()
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
        mtime: Optional[float] = None,
        birthtime: Optional[float] = None,
    ) -> int:
        """Delete stale rows and re-embed the content of one file. Idempotent.

        Diary logs are indexed one row per fact (§A); notebook pages and core files
        one row per paragraph chunk. Tombstoned content is skipped for every source
        type (diary facts AND notebook/core chunks alike) so a user deletion never
        resurrects, even on a full clear-and-rebuild. Returns the number of rows indexed.
        """
        tombstones = tombstones or set()
        source_time = self._source_time(label, filename, content, mtime, birthtime)

        # 1. Build the rows to index: (text, metadata, importance). Daily-log facts
        #    are raw capture with no lifecycle, so they stay at the neutral 0.5;
        #    vault pages are scored from the signals the dream records on them.
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
            category, tags = self._page_taxonomy(label, filename, content)
            # Vault pages carry a lifecycle (frontmatter status/stale_after, inline
            # confirmation counts). Core files carry none of that, with one exception:
            # MEMORY.md's manual zone is where a person edits their own memory, and
            # `write_memory_manual_zone` stamps it with a `human:` actor. Everything
            # else on this path stays on the neutral default.
            lifecycle = (
                self._parse_page_lifecycle(content) if source_type == "notebook" else {}
            )
            if source_type == "notebook":
                segments = [(content, lifecycle)]
            else:
                # Chunked per zone, not per file: `_chunk_by_paragraphs` merges short
                # paragraphs, so chunking MEMORY.md whole produces a single row
                # spanning the generated half and the human half — one row that is
                # both machine output and user-verified, which is neither.
                segments = self._provenance_segments(content)

            rows = []
            i = 0
            for segment, claim_lifecycle in segments:
                for chunk in self._chunk_by_paragraphs(segment):
                    i += 1
                    if (
                        not chunk.strip()
                        or " ".join(chunk.lower().split()) in tombstones
                    ):
                        continue
                    rows.append(
                        (
                            chunk,
                            {
                                "source_type": source_type,
                                "source_file": filename,
                                "chunk_index": i,
                                "label": label,
                                "category": category,
                                "tags": tags,
                                **claim_lifecycle,
                            },
                            self._claim_strength(chunk, claim_lifecycle)
                            if claim_lifecycle
                            else 0.5,
                        )
                    )

        # 2. Archive logs are appended to many times a day, and every append used to
        #    re-embed the whole file: ~28x more embedding calls than facts across the
        #    real corpus, quadratic in appends per day, and hundreds of thousands of
        #    single-row inserts fragmenting the table. Diff against what is already
        #    indexed instead. Correctness is unchanged — the end state is the same set
        #    of rows — and a diff that comes back empty degrades to the old full
        #    replace, so a failed query costs work, never accuracy.
        if label == "archive":
            replaced = await self._sync_archive_rows(
                filename, rows, lancedb_store, embedding_gen, user_id, source_time
            )
            if replaced is not None:
                return replaced

        # 3. Embed ALL rows BEFORE mutating the index. embedding_gen.generate() raises
        #    on failure (e.g. embedding backend unreachable) — letting it propagate here
        #    leaves the existing index untouched and the file gets retried next pass,
        #    instead of deleting rows and replacing them with poisoned zero vectors.
        embeddings = [await embedding_gen.generate(text) for text, _, _ in rows]

        # 4. Replace: clear this file's old rows, then add the freshly-embedded ones.
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
                created_at=source_time,
            )
            indexed += 1

        return indexed

    async def _sync_archive_rows(
        self,
        filename: str,
        rows: List[tuple],
        lancedb_store,
        embedding_gen,
        user_id: str,
        source_time: Optional[datetime] = None,
    ) -> Optional[int]:
        """Bring one daily log's rows in line by diffing, not by re-embedding it.

        Returns the row count now indexed for the file, or None to fall back to the
        full delete-then-add path. None is returned whenever the diff cannot be
        trusted — the store has no `list_source_rows`, the query failed, or the index
        holds nothing for this date yet (a first index, where the diff would be the
        whole file anyway).
        """
        date = filename.removesuffix(".md")
        lister = getattr(lancedb_store, "list_source_rows", None)
        if lister is None:
            return None
        try:
            existing = await lister(date, user_id)
        except Exception as e:
            logger.warning(f"Archive diff unavailable for {date}; full reindex: {e}")
            return None
        if not existing:
            return None

        # Duplicate content within one day collapses to a single key. That matches
        # what the search index should hold anyway, and the extra copies get dropped
        # here as stale — the log itself keeps every line.
        #
        # A row without `source_file` is never a match, however identical its text.
        # It is a pre-June direct insert that no file owns: nothing will ever reindex
        # it, and `retire_legacy_rows.py --export` writes its text into this very log
        # precisely so an owned row can replace it. Counting it as already-indexed
        # would skip that replacement, and the export's `--apply` would then delete
        # the only copy. So it is retired here and the line re-added under the file.
        indexed: dict = {}
        stale_ids: List[str] = []
        for row in existing:
            key = " ".join(str(row.get("content", "")).lower().split())
            if not _owned_by_file(row):
                stale_ids.append(row.get("id"))
                continue
            if not key or key in indexed:
                stale_ids.append(row.get("id"))
                continue
            indexed[key] = row.get("id")

        wanted = {
            " ".join(text.lower().split()): (text, meta, imp)
            for text, meta, imp in rows
        }

        for key, row_id in indexed.items():
            if key not in wanted and row_id:
                stale_ids.append(row_id)

        added = 0
        for key, (text, metadata, importance) in wanted.items():
            if key in indexed:
                continue
            embedding = await embedding_gen.generate(text)
            await lancedb_store.add_memory(
                content=text,
                embedding=embedding,
                user_id=user_id,
                chat_id=None,
                metadata=metadata,
                importance=importance,
                created_at=source_time,
            )
            added += 1

        # Removals last: a crash before this point leaves rows that a later pass will
        # clear, whereas deleting first could drop a fact that never gets re-added.
        for row_id in stale_ids:
            try:
                await lancedb_store.delete_memory(row_id)
            except Exception as e:
                logger.warning(f"Could not delete stale row {row_id}: {e}")

        if added or stale_ids:
            logger.debug(
                f"Archive {date}: +{added} -{len(stale_ids)} (diffed, "
                f"{len(wanted)} facts in file)"
            )
        return len(wanted)

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

    # Vault zone → what the pages in it are *about*. The zone is the only signal
    # every page has; `type:` in frontmatter overrides it where present.
    ZONE_CATEGORIES: dict = {
        "0_Inbox": "inbox",
        "1_Projects": "project",
        "2_Wiki": "knowledge",
        "3_Personal": "personal",
        "4_Assets": "asset",
        "5_Archives": "archive",
    }
    KNOWN_PAGE_TYPES: set = {
        "concept",
        "synthesis",
        "entity",
        "literature",
        "project",
        "personal",
        "documentation",
    }

    @staticmethod
    def file_times(path: Path) -> tuple:
        """`(mtime, birthtime)` for a file, either of which may be None.

        Birth time is a real field on Windows and macOS. Linux exposes it only on
        newer kernels and filesystems, and `st_ctime` there is inode-change time —
        which a rewrite also moves — so it is deliberately not used as a stand-in.
        """
        try:
            st = path.stat()
        except OSError:
            return None, None
        birth = getattr(st, "st_birthtime", None)
        return st.st_mtime, birth

    @classmethod
    def _source_time(
        cls,
        label: str,
        filename: str,
        content: str,
        mtime: Optional[float] = None,
        birthtime: Optional[float] = None,
    ) -> Optional[datetime]:
        """When the content dates from — not when we happen to be embedding it.

        Indexing is not authorship. A vault page written last October and re-embedded
        today is still from last October, and stamping it with the write time is what
        makes a reindex read as a flood of brand-new memories.

        A daily log is exact: its date is its filename. Everything else takes the
        *earliest* plausible signal among frontmatter dates, file birth time, and
        mtime — not the first one found in a priority order.

        Earliest, because this column is `created_at` and every one of those signals
        is an upper bound on creation. mtime especially: the dream rewrites vault
        pages in place, so a page it touched this morning has today's mtime and a
        birth time from January. Preferring mtime made exactly those pages — the ones
        the agent works on most — permanently claim to be new.

        Returns None when nothing is available, which leaves `add_memory` on its
        write-time default.
        """
        if label == "archive":
            try:
                return datetime.strptime(
                    filename.removesuffix(".md"), "%Y-%m-%d"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        candidates = []

        m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", content, re.DOTALL)
        if m:
            for key in ("created", "date", "updated"):
                stamp = re.search(
                    rf"^{key}\s*:\s*['\"]?(\d{{4}}-\d{{2}}-\d{{2}})", m.group(1), re.M
                )
                if stamp:
                    try:
                        candidates.append(
                            datetime.strptime(stamp.group(1), "%Y-%m-%d").replace(
                                tzinfo=timezone.utc
                            )
                        )
                    except ValueError:
                        continue

        for stamp in (birthtime, mtime):
            if stamp is None:
                continue
            try:
                candidates.append(datetime.fromtimestamp(stamp, tz=timezone.utc))
            except (OverflowError, OSError, ValueError):
                continue

        # A timestamp before the epoch-ish floor is a filesystem artefact (copied
        # archives land at 1980), and one in the future is a clock skew or a typo.
        # Either would win an earliest-wins vote outright, so both are discarded.
        now = datetime.now(timezone.utc)
        floor = datetime(2000, 1, 1, tzinfo=timezone.utc)
        credible = [c for c in candidates if floor <= c <= now]
        return min(credible) if credible else None

    @classmethod
    def _page_taxonomy(cls, label: str, filename: str, content: str) -> tuple:
        """`(category, tags)` for a notebook page or core file.

        Category answers "what kind of thing is this", which is what a reader filters
        on. It deliberately does *not* answer "where did this come from" — that is
        `source_type`, already its own field. Filenames and source labels are excluded
        from tags for the same reason: a tag every row in a source shares carries no
        information, and one that is unique per row cannot group anything.
        """
        if label != "notebook":
            return "profile", []

        frontmatter = {}
        m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", content, re.DOTALL)
        if m:
            for line in m.group(1).splitlines():
                kv = re.match(r"^(type|tags)\s*:\s*(.+?)\s*$", line.strip())
                if kv:
                    frontmatter[kv.group(1)] = kv.group(2).strip().strip("\"'")

        zone = filename.replace("\\", "/").split("/")[0]
        category = cls.ZONE_CATEGORIES.get(zone, "knowledge")
        declared = frontmatter.get("type", "").strip().lower()
        if declared in cls.KNOWN_PAGE_TYPES:
            category = declared

        tags = []
        raw = frontmatter.get("tags", "")
        for tag in re.split(r"[,\s]+", raw.strip("[]")):
            tag = tag.strip().strip("\"'#").lower()
            if tag and tag not in tags:
                tags.append(tag)
        return category, tags[:8]

    @staticmethod
    def _parse_page_lifecycle(content: str) -> dict:
        """Read `status` and `stale_after` out of a vault page's frontmatter.

        Deliberately not a YAML parse: the frontmatter is hand-editable and a page with
        a malformed block must still be indexed. Unreadable keys simply go missing,
        which lands the page on the neutral defaults.
        """
        lifecycle: dict = {}
        m = re.match(r"^---\s*\n(.*?)\n---\s*(\n|$)", content, re.DOTALL)
        if not m:
            return lifecycle
        for line in m.group(1).splitlines():
            kv = re.match(
                r"^(status|stale_after|verified_by|verified_at)\s*:\s*(.+?)\s*$",
                line.strip(),
            )
            if kv:
                lifecycle[kv.group(1)] = kv.group(2).strip().strip("\"'")
        return lifecycle

    @staticmethod
    def _provenance_segments(content: str) -> List[tuple]:
        """Split a core file into `(text, lifecycle)` regions by who wrote them.

        MEMORY.md is the only file with two authors: a generated zone rewritten on
        every consolidation, and a manual zone a person edits and `write_memory_manual_zone`
        stamps with a `human:` actor. Only the region *after* the end marker carries
        that verification — everything above it is machine output, and scoring it as
        human-verified would launder the generator's own text into the strongest
        evidence class the ranker has. Every other core file comes back as one
        unstamped segment, which is the neutral default it had before.
        """
        from .markdown_store import MEMORY_GENERATED_END

        if MEMORY_GENERATED_END not in content:
            return [(content, {})]
        head, _, tail = content.partition(MEMORY_GENERATED_END)
        verification = CoreMemoryFileIndexer._parse_verification(tail)
        return [(head, {}), (tail, verification)]

    @staticmethod
    def _parse_verification(content: str) -> dict:
        """Read the `<!-- verified: <actor> at <ts> -->` stamp, if the text carries one.

        Written by `write_memory_manual_zone` when a person edits MEMORY.md, which is
        the only place in the system where a claim comes from the user directly rather
        than from extraction. Returned in the same shape as the frontmatter lifecycle
        so both paths feed `_claim_strength` through one argument.
        """
        m = re.search(
            r"<!--\s*verified:\s*(.+?)\s+at\s+(\S+?)\s*-->", content, re.IGNORECASE
        )
        if not m:
            return {}
        return {"verified_by": m.group(1).strip(), "verified_at": m.group(2).strip()}

    @staticmethod
    def _claim_strength(
        chunk: str, lifecycle: dict, today: Optional[str] = None
    ) -> float:
        """Importance for one vault chunk, from the signals the dream writes.

        `importance` is already a scoring term in hybrid search (`importance_boost`),
        and until now every row carried a constant 0.5 — so a claim confirmed twelve
        times ranked exactly like a one-off, and a claim months past its expiry ranked
        exactly like one confirmed yesterday. This is the read side of the lifecycle
        the writer has been recording since `07f24c4b`.

        Bounded to [0.1, 1.0] on purpose. Nothing here can push a claim out of
        retrieval — `deprecated` demotes, it does not delete, and deletion stays with
        tombstones so it remains reversible and auditable.
        """
        score = 0.5

        # A repeated fact is one claim confirmed many times, not many facts. Log-scaled
        # so the difference between 1x and 5x matters and 40x vs 60x does not.
        confirmations = 0
        for m in re.finditer(r"\(confirmed\s+(\d+)x", chunk, re.IGNORECASE):
            confirmations = max(confirmations, int(m.group(1)))
        if confirmations > 1:
            score += min(0.25, 0.08 * math.log2(confirmations))

        # Only `deprecated` and `draft` change the score. Everything else — `stable`,
        # the `active` the live vault actually wrote before the schema said `stable`,
        # a typo, nothing at all — is neutral: a page is never demoted for predating a
        # rule, and an unrecognised status is missing information, not bad evidence.
        status = (lifecycle.get("status") or "").lower()
        if status == "deprecated":
            # A softer tombstone: still readable and linkable, out of the running.
            return 0.1
        if status == "draft":
            score -= 0.05

        # A person typed this. That outranks every other signal here: confirmation
        # counts, extraction confidence and expiry dates are all evidence *about* a
        # claim, whereas this is the claim's subject stating it directly. It takes a
        # floor rather than a bonus so it cannot be diluted by a low base score, and
        # it skips the staleness decay below — an expiry says "nobody has re-confirmed
        # this lately", which is exactly the thing a human verification answers.
        # `deprecated` still wins, above: a person retiring a claim is also a person.
        if (lifecycle.get("verified_by") or "").lower().startswith("human:"):
            return max(HUMAN_VERIFIED_FLOOR, min(1.0, score))

        # Past its stale_after the claim is not wrong, just unverified — decay it
        # rather than dropping it, and let the revisit queue confirm or deprecate.
        stale_after = lifecycle.get("stale_after", "")
        if re.match(r"^\d{4}-\d{2}-\d{2}", stale_after):
            now = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if stale_after[:10] < now:
                score *= 0.6

        return max(0.1, min(1.0, score))

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
