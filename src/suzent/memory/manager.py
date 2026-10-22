"""
Memory Manager - orchestrates core and archival memory operations.
"""

from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from datetime import datetime, timedelta, timezone

from suzent.logger import get_logger
from suzent.llm import EmbeddingGenerator, LLMClient
from .lancedb_store import LanceDBMemoryStore
from .markdown_store import MarkdownMemoryStore
from .indexer import CoreMemoryFileIndexer
from .classifier import classify_fact
from . import capture, memory_context, memory_map
from .models import (
    ExtractedFact,
    ConversationContext,
    MemoryExtractionResult,
    FactExtractionResponse,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from .wiki_manager import WikiManager

# Memory system constants
DEFAULT_MEMORY_RETRIEVAL_LIMIT = 5
DEFAULT_MEMORY_SEARCH_LIMIT = 10

# Heuristic extraction importance scores
DEFAULT_IMPORTANCE = 0.5

# Extraction settings
LLM_EXTRACTION_TEMPERATURE = 1.0

# Already-known facts shown to the extractor so a re-mention is not stored again.
# Ten is enough to cover the stable identity/preference facts that dominate the
# duplicate clusters without crowding out the turn itself.
KNOWN_FACTS_LIMIT = 10
KNOWN_FACTS_MAX_CHARS = 240
KNOWN_FACTS_QUERY_CHARS = 2000

# Sources where a matched claim is already written down for good. A transcript row is
# the user saying something, and MEMORY.md is generated from other rows -- neither is a
# record the write path can defer to.
DURABLE_SOURCE_TYPES = frozenset({"notebook", "archive_log"})
PAGE_SOURCE_TYPES = frozenset({"notebook", "core_file"})

# How close a stored row must be to a retraction to be hidden with it. Looser than
# capture's restatement check: the user describes the claim, rarely quotes it.
RETRACT_MATCH = 0.6

# Rendered core-memory prompts retained at once. Comfortably above the number of
# chats one service handles concurrently, while keeping the ceiling explicit.
CORE_MEMORY_CACHE_MAXSIZE = 256


class MemoryManager:
    """Central memory management service.

    Manages both core memory blocks (always-visible working memory) and
    archival memory (unlimited searchable storage with vector embeddings).

    Key principle: Agents recall memories via search, but don't manage them explicitly.
    Memory operations happen automatically or via dedicated update tools.
    """

    def __init__(
        self,
        store: LanceDBMemoryStore,
        embedding_model: str = None,
        embedding_dimension: int = 0,
        llm_for_extraction: Optional[str] = None,
        markdown_store: Optional[MarkdownMemoryStore] = None,
    ):
        """Initialize memory manager.

        Args:
            store: LanceDB store instance
            embedding_model: LiteLLM model identifier for embeddings
            embedding_dimension: Expected embedding dimension (0 = auto-detect)
            llm_for_extraction: LLM model for fact extraction (uses LLM if provided)
            markdown_store: Optional markdown-based memory store for human-readable persistence
        """
        self.store = store
        self.markdown_store = markdown_store
        # (chat_id, user_id, sandbox_enabled, *resolver paths) -> (revision, text).
        # An LRU, not a plain dict: keys outlive the thing they describe. Deleted
        # chats leave entries behind, and a chat that changes its cwd or notebook
        # mount strands its previous key forever, so in a long-running service the
        # footprint would track historical chat/path combinations rather than live
        # ones. Each entry holds a full rendered prompt, so that adds up.
        self._core_memory_cache: "OrderedDict[tuple, tuple]" = OrderedDict()
        self.embedding_gen = EmbeddingGenerator(
            model=embedding_model, dimension=embedding_dimension
        )
        self.llm_extraction_model = llm_for_extraction
        self.llm_client = (
            LLMClient(model=llm_for_extraction) if llm_for_extraction else None
        )
        self.wiki_manager: Optional["WikiManager"] = None
        # Shared indexer instance (also used by the lifecycle background watcher and
        # the dream runner) — the SOLE writer to the LanceDB search index.
        self._core_indexer = CoreMemoryFileIndexer()
        logger.info(
            f"MemoryManager initialized with embedding model: {embedding_model}, "
            f"extraction model: {llm_for_extraction}, "
            f"markdown: {'enabled' if markdown_store else 'disabled'}"
        )

    def set_extraction_model(self, model: str | None) -> None:
        """Apply role changes without rebuilding stores or background workers."""
        if model == self.llm_extraction_model:
            return
        client = LLMClient(model=model) if model else None
        self.llm_extraction_model = model
        self.llm_client = client

    # ===== Core Memory Blocks (File-based SSoT) =====

    # Default content when a block file does not yet exist
    _BLOCK_DEFAULTS: Dict[str, str] = {
        "persona": "You are Suzent, a helpful AI assistant with long-term memory.",
        "user": "No user information yet.",
        "facts": "No facts stored yet.",
        "context": "No current context.",
    }

    async def get_core_memory(
        self, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get core memory blocks from markdown files (file-based SSoT).

        Reads:
          - persona.md  → 'persona' block
          - user.md     → 'user' block
          - MEMORY.md   → 'facts' block
          - projects/{slug}/context.md → 'context' block (only when chat_id given)
        """
        blocks: Dict[str, str] = {}

        if self.markdown_store:
            # Global blocks — files in shared memory directory
            for label in ("persona", "user"):
                content = await self.markdown_store.read_block(label)
                if content is not None:
                    blocks[label] = content

            # Facts ← MEMORY.md
            memory_file = await self.markdown_store.read_memory_file()
            if memory_file is not None:
                blocks["facts"] = memory_file

            # Context ← project-scoped (only when chat_id available)
            if chat_id:
                ctx = await self.markdown_store.read_session_context(chat_id)
                if ctx is not None:
                    blocks["context"] = ctx
        else:
            # Fallback: read from LanceDB memory_blocks table (legacy path)
            blocks = await self.store.get_all_memory_blocks(
                chat_id=chat_id, user_id=user_id
            )

        # Apply defaults for any missing blocks
        for label, default_content in self._BLOCK_DEFAULTS.items():
            if label not in blocks:
                blocks[label] = default_content

        return blocks

    async def update_memory_block(
        self,
        label: str,
        content: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """Update a core memory block by writing its corresponding markdown file."""
        try:
            if self.markdown_store:
                if label == "context":
                    if chat_id:
                        await self.markdown_store.write_session_context(
                            chat_id, content
                        )
                    else:
                        # No chat_id — skip silently (context is always session-scoped)
                        logger.debug("Skipping context write: no chat_id provided")
                elif label == "facts":
                    await self.markdown_store.write_memory_map(content)
                else:
                    await self.markdown_store.write_block(label, content)
            else:
                # Fallback: persist to LanceDB memory_blocks table
                await self.store.set_memory_block(
                    label=label, content=content, chat_id=chat_id, user_id=user_id
                )

            logger.info(
                f"Updated core memory block '{label}' for user={user_id}, chat={chat_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update memory block '{label}': {e}")
            return False

    async def ensure_memory_map(self) -> bool:
        """Draft MEMORY.md from page titles when it is missing or empty.

        Returns whether a draft was written. An existing file is left alone even when
        it is not a map yet; lint reports it and the cleanup drafts convert it.
        """
        store = self.markdown_store
        if not store:
            return False
        draft = memory_map.draft_map(store.notebook_dir, store.list_notebook_pages())
        return await store.write_memory_map_if_missing(draft)

    async def lint_memory_files(self) -> List[memory_map.Finding]:
        """Contract findings for MEMORY.md, the always-injected files and page sizes."""
        store = self.markdown_store
        if not store:
            return []
        from suzent.config import CONFIG

        return await memory_map.lint_store(store, max_lines=CONFIG.memory_map_max_lines)

    @staticmethod
    def _resolver_paths(sandbox_enabled: bool, path_resolver) -> tuple:
        """Paths the core-memory section renders, as the resolver sees them now.

        Host mode bakes the working directory and notebook mount into the prompt,
        so these are part of the section's identity, not incidental formatting: a
        chat that changes its authorized cwd renders different text from the very
        same memory files.
        """
        if sandbox_enabled or path_resolver is None:
            return (None, None, "/workspace/context.md" if sandbox_enabled else None)

        shared_path = str(path_resolver.sandbox_data_path / "shared").replace("\\", "/")
        mount_notebook = (
            str(path_resolver.custom_mounts.get("/mnt/notebook", "")).replace("\\", "/")
            or None
        )
        # project_dir, not get_working_dir(): context.md is read back through
        # MarkdownMemoryStore.read_session_context(), which always resolves to the
        # chat's project directory. A chat pointed at an authorized cwd has a
        # different get_working_dir(), so rendering that would tell the agent to
        # write somewhere nothing ever reads.
        project_context_path = str(path_resolver.project_dir / "context.md").replace(
            "\\", "/"
        )
        return (shared_path, mount_notebook, project_context_path)

    async def format_core_memory_for_context(
        self,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        sandbox_enabled: bool = True,
        path_resolver=None,
        notebook_skill_available: bool = False,
    ) -> str:
        """Format core memory as text for prompt injection."""
        try:
            blocks = await self.get_core_memory(chat_id=chat_id, user_id=user_id)
        except Exception as e:
            logger.error(f"Error getting core memory blocks: {e}")
            return ""

        shared_path, mount_notebook, project_context_path = self._resolver_paths(
            sandbox_enabled, path_resolver
        )

        return memory_context.format_core_memory_section(
            blocks,
            sandbox_enabled=sandbox_enabled,
            chat_id=chat_id,
            shared_path=shared_path,
            mount_notebook=mount_notebook,
            project_context_path=project_context_path,
            notebook_skill_available=notebook_skill_available,
            open_questions=(
                self.markdown_store.read_review_queue() if self.markdown_store else None
            ),
        )

    async def get_core_memory_context(
        self,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        sandbox_enabled: bool = True,
        path_resolver=None,
        notebook_skill_available: bool = False,
    ) -> str:
        """Core-memory prompt section for a chat, rebuilt when its files change.

        ``format_core_memory_for_context`` reads four files and re-renders the
        whole section, which is too much to repeat on every model request. This
        wraps it in a cache keyed by the scope that actually varies, invalidated
        by ``core_memory_revision()`` so an edit to persona.md or MEMORY.md shows
        up on the very next turn.

        Falls through to an uncached render whenever there is no markdown store
        (the legacy LanceDB path), where no cheap revision exists.
        """
        store = self.markdown_store
        if store is None:
            return await self.format_core_memory_for_context(
                chat_id=chat_id,
                user_id=user_id,
                sandbox_enabled=sandbox_enabled,
                path_resolver=path_resolver,
                notebook_skill_available=notebook_skill_available,
            )

        # Host mode renders the working directory and notebook mount into the
        # section, so a chat that changes its authorized cwd must not be served
        # the previous paths just because the memory files are untouched.
        # notebook_skill_available changes the rendered text, so it is part of
        # the identity. Keying only on memory-file revisions meant toggling the
        # skill left every existing chat on the previous wording indefinitely.
        key = (
            chat_id,
            user_id,
            sandbox_enabled,
            notebook_skill_available,
        ) + self._resolver_paths(sandbox_enabled, path_resolver)
        try:
            revision = store.core_memory_revision(chat_id)
        except Exception as e:
            logger.debug(f"Core memory revision unavailable, rebuilding: {e}")
            revision = None

        if revision is not None:
            cached = self._core_memory_cache.get(key)
            if cached is not None and cached[0] == revision:
                self._core_memory_cache.move_to_end(key)
                return cached[1]

        rendered = await self.format_core_memory_for_context(
            chat_id=chat_id,
            user_id=user_id,
            sandbox_enabled=sandbox_enabled,
            path_resolver=path_resolver,
            notebook_skill_available=notebook_skill_available,
        )
        # format_core_memory_for_context() swallows read errors and returns "".
        # Caching that under an unchanged revision would turn one bad request into
        # a chat with no core memory until some unrelated file happens to change.
        if revision is not None and rendered:
            self._core_memory_cache[key] = (revision, rendered)
            self._core_memory_cache.move_to_end(key)
            while len(self._core_memory_cache) > CORE_MEMORY_CACHE_MAXSIZE:
                self._core_memory_cache.popitem(last=False)
        return rendered

    def _log_recalls(self, memories: List[Dict[str, Any]]) -> None:
        """Record retrieved memories to the recall log (usage signal for the map
        lint). Best-effort — never raises."""
        if not self.markdown_store or not memories:
            return
        try:
            for m in memories:
                if not isinstance(m, dict):
                    continue
                meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
                self.markdown_store.append_recall(
                    m.get("content", ""),
                    meta.get("source_type", ""),
                    meta.get("source_file", ""),
                )
        except Exception:
            pass

    async def retrieve_relevant_memories(
        self,
        query: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = DEFAULT_MEMORY_RETRIEVAL_LIMIT,
        use_embedding: bool = True,
    ) -> str:
        """
        Automatically retrieve and format relevant memories for a query.
        This is called before the agent processes the message to inject context.

        Args:
            query: User's input query
            chat_id: Optional chat context
            user_id: User identifier
            limit: Maximum number of memories to retrieve
            use_embedding: When True (default), use hybrid embedding+FTS search.
                When False, use FTS-only (local, no API call) — suitable for
                per-turn auto-injection where latency matters most.

        Returns:
            Formatted string with relevant memories, or empty string if none found
        """
        try:
            import time

            # Fast exit: if the archival store has no memories at all, skip
            # entirely — no point searching with nothing in the index.
            t0 = time.monotonic()
            count = await self.store.get_memory_count(user_id=user_id)
            logger.debug(
                f"[retrieve_relevant_memories] get_memory_count={count} elapsed={time.monotonic() - t0:.3f}s"
            )
            if count == 0:
                return ""

            if use_embedding:
                memories = await self.search_memories(
                    query=query, limit=limit, chat_id=chat_id, user_id=user_id
                )
            else:
                t1 = time.monotonic()
                memories = await self.store.fts_search(
                    query_text=query, user_id=user_id or "", chat_id=None, limit=limit
                )
                logger.debug(
                    f"[retrieve_relevant_memories] fts_search elapsed={time.monotonic() - t1:.3f}s results={len(memories)}"
                )

            if not memories:
                return ""

            self._log_recalls(memories)
            logger.info(f"Retrieved {len(memories)} relevant memories for query")
            return memory_context.format_retrieved_memories_section(
                memories, tag_important=True
            )

        except Exception as e:
            logger.error(f"Failed to retrieve relevant memories: {e}")
            return ""

    # ===== Archival Memory Search (Agent-facing) =====

    async def search_memories(
        self,
        query: str,
        limit: int = DEFAULT_MEMORY_SEARCH_LIMIT,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        use_hybrid: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for memories (agent-facing tool).
        Uses hybrid search when embeddings are configured; otherwise falls back
        to local full-text search so memory remains useful without an embedding
        provider.
        """
        try:
            if not self.embedding_gen.model:
                results = await self.store.fts_search(
                    query_text=query,
                    user_id=user_id or "",
                    chat_id=chat_id,
                    limit=limit,
                )
                self._log_recalls(results)
                logger.info(
                    f"Keyword memory search for '{query}': found {len(results)} results"
                )
                return results

            # Generate query embedding
            query_embedding = await self.embedding_gen.generate(query)

            if use_hybrid:
                # Hybrid search (semantic + full-text)
                results = await self.store.hybrid_search(
                    query_embedding=query_embedding,
                    query_text=query,
                    user_id=user_id,
                    chat_id=chat_id,
                    limit=limit,
                )
            else:
                # Pure semantic search
                results = await self.store.semantic_search(
                    query_embedding=query_embedding,
                    user_id=user_id,
                    chat_id=chat_id,
                    limit=limit,
                )

            self._log_recalls(results)
            logger.info(f"Memory search for '{query}': found {len(results)} results")
            return results

        except Exception as e:
            import traceback

            logger.error(f"Memory search failed: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return []

    # ===== Automatic Memory Management (Internal) =====

    async def process_conversation_for_memories(
        self,
        conversation_text: str,
        chat_id: str,
        user_id: str,
        recall_query: Optional[str] = None,
    ) -> MemoryExtractionResult:
        """
        Extract and store the important facts from a stretch of conversation.

        Args:
            conversation_text: The turns to analyze, formatted for the extractor
            chat_id: Chat identifier
            user_id: User identifier
            recall_query: Text to find already-known facts with; defaults to
                *conversation_text*

        Returns:
            MemoryExtractionResult with the list of extracted fact contents.

        Raises when the extraction model fails, so the caller can keep the turns
        and retry them.

        Append-only write path (fixes #34): facts are written to the markdown daily
        log (the source of truth) and indexed into LanceDB. There is still NO
        write-time deduplication — an update to a fact must never be silently
        dropped, which is what #34 was. Repetition is suppressed one step earlier
        instead, by showing the extractor what memory already holds so a re-mention
        is not extracted at all. What survives that is resolved by the dream
        consolidation pass. See docs/03-features/memory/README.md and
        docs/08-developing/architecture/memory-architecture.md.
        """
        result = MemoryExtractionResult.empty()

        try:
            # Show the model what memory already holds so a re-mention is not
            # stored as a new fact.
            known = await self._recall_known_facts(
                recall_query or conversation_text, user_id, chat_id
            )
            # Only the durable ones. The prompt tells the model not to re-extract what
            # it is shown, and a fact that exists solely in a transcript or in the
            # generated MEMORY.md is not recorded anywhere the write path is about to
            # record it -- suppressing it there means it never reaches the append-only
            # log at all, and `_split_confirmations` cannot recover a fact the model
            # already declined to emit.
            durable_known = [k["content"] for k in known if k.get("durable")]
            mode = self._capture_mode()
            if mode == "typed":
                extracted_facts = await self._capture_facts(
                    conversation_text, durable_known
                )
            else:
                extracted_facts = await self._extract_facts_llm(
                    conversation_text, durable_known
                )
                if mode == "shadow":
                    await self._shadow_capture(
                        conversation_text, durable_known, extracted_facts, chat_id
                    )

            if not extracted_facts:
                logger.debug("No facts extracted from conversation")
                return result

            # Separate out the re-statements. What is left keeps the append-only path.
            extracted_facts, confirmations = await self._split_confirmations(
                extracted_facts, known, chat_id
            )
            result.confirmed_facts = [c[0] for c in confirmations]

            if not extracted_facts:
                logger.debug(
                    f"Conversation held only re-statements: {len(confirmations)} confirmed"
                )
                return result

            result.extracted_facts = [f.content for f in extracted_facts]
            logger.debug(
                f"Extracted {len(extracted_facts)} facts: {result.extracted_facts}"
            )

            # 1. Append to the markdown daily log (append-only source of truth).
            date = await self._write_facts_to_markdown(extracted_facts, chat_id)

            # 2. Index the day's log into LanceDB (the derived search index).
            if date:
                await self._index_daily_log(date, user_id)

            logger.info(
                f"Processed conversation: extracted {len(result.extracted_facts)} facts"
            )

        except Exception as e:
            logger.error(f"Failed to process conversation for memories: {e}")
            import traceback

            logger.error(traceback.format_exc())
            raise

        return result

    async def _index_daily_log(self, date: str, user_id: str) -> None:
        """Reindex one day's log. The indexer is the only writer to LanceDB."""
        if not self.markdown_store:
            return
        try:
            await self._core_indexer.reindex_file_now(
                markdown_store=self.markdown_store,
                lancedb_store=self.store,
                embedding_gen=self.embedding_gen,
                user_id=user_id,
                label="archive",
                filename=f"{date}.md",
            )
        except Exception as e:
            logger.warning(f"Failed to index daily log {date}: {e}")

    async def apply_memory_update(
        self,
        *,
        user_id: str,
        chat_id: str,
        fact: Optional[str] = None,
        retract: Optional[str] = None,
        retract_as: str = "wrong",
        kind: str = "user",
        category: str = "context",
        horizon: str = "durable",
        evidence: str = "",
    ) -> Dict[str, Any]:
        """Record what the user asked to remember, retract or correct, or what the
        agent learned from an outcome or a source it read.

        One entry point for all of them: a correction is a retraction plus the fact that
        replaces it. *kind* sets the provenance tags the dream routes by; only a User
        fact is marked `explicit`, since only the user can vouch for one. A retraction
        tombstones the matching log rows so search stops returning them; a claim on a
        notebook page is left for the dream to remove, since its chunk holds other
        claims too. One marked *wrong* also goes on the rejected list, so capture,
        the dream and lint keep it from coming back. *outdated* only hides it: the claim
        was true once and the dream may still keep it as history.

        Returns `{"retracted": [...], "written": str | None}`.
        """
        if not self.markdown_store:
            raise RuntimeError("Memory files are not available")
        store = self.markdown_store
        now = datetime.now(timezone.utc)
        date = now.strftime("%Y-%m-%d")
        retracted: List[str] = []

        if retract and retract.strip():
            retract = " ".join(retract.split())
            if retract_as == "wrong":
                await store.append_rejected(retract, date)
            key = capture.normalize(retract)
            matches = await self.search_memories(
                query=retract, limit=KNOWN_FACTS_LIMIT, user_id=user_id
            )
            archive_days: set = set()
            for row in matches:
                content = str(row.get("content", ""))
                body = capture.normalize(content)
                meta = row.get("metadata") or {}
                # A page chunk coalesces many claims; tombstoning it would hide them
                # all. The dream removes the claim from the page instead.
                if meta.get("source_type") in PAGE_SOURCE_TYPES:
                    continue
                if not body or not (
                    key in body or capture.similarity(key, body) >= RETRACT_MATCH
                ):
                    continue
                await store.append_tombstone(content)
                retracted.append(content)
                source_file = meta.get("source_file")
                if meta.get("source_type") == "archive_log" and source_file:
                    archive_days.add(Path(source_file).stem)
                elif row.get("id"):
                    await self.store.delete_memory(row["id"])
            await store.append_tombstone(retract)
            for day in archive_days:
                await self._index_daily_log(day, user_id)

        written: Optional[str] = None
        if fact and fact.strip():
            written = " ".join(fact.split())
            match kind:
                case "experience":
                    tags = ["kind:experience", "source:outcome"]
                case "world":
                    tags = ["kind:world", "source:tool_output"]
                case _:
                    tags = ["kind:user", "source:user_said", "explicit"]
            if horizon == "dated":
                stale = now + timedelta(days=capture.DATED_STALE_DAYS)
                tags += ["dated", f"stale_after:{stale.strftime('%Y-%m-%d')}"]
            if retract:
                tags.append("revision")
            await store.append_daily_log(
                chat_id=chat_id or "memory_update",
                facts=[
                    {
                        "content": written,
                        "category": category,
                        "tags": tags,
                        "evidence": evidence,
                    }
                ],
                date=date,
            )
            await self._index_daily_log(date, user_id)

        logger.info(
            f"memory_update: retracted {len(retracted)} row(s)"
            + (", wrote one fact" if written else "")
        )
        return {"retracted": retracted, "written": written}

    async def _split_confirmations(
        self,
        facts: List[ExtractedFact],
        known: List[Dict[str, Any]],
        chat_id: str,
    ) -> tuple:
        """Divide extracted facts into ones to write and ones already on record.

        Returns `(to_write, confirmations)`. A fact is a confirmation only when it
        matches a *durably recorded* claim in the same words with no new specifics
        (see `classifier.classify_fact`); it then becomes a line in the confirmations
        sidecar instead of a redundant row in the daily log. Nothing is lost by that:
        the identical text is already in a vault page or an earlier log, and the fact
        that it recurred is what the sidecar records.

        A revision is written exactly as before — issue #34 was a write-time dedup that
        swallowed an update, and nothing here is allowed to do that again. It is only
        tagged, so the dream knows to treat it as an update to a claim it already holds.

        Best-effort: if the sidecar write fails, the fact falls back to the normal
        append-only path.
        """
        if not self.markdown_store or not known:
            return facts, []

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        durable = [k["content"] for k in known if k.get("durable")]
        to_write: List[ExtractedFact] = []
        confirmations: List[tuple] = []

        for fact in facts:
            verdict = classify_fact(fact.content, durable)
            if verdict.is_confirmation:
                try:
                    await self.markdown_store.append_confirmation(
                        content=fact.content,
                        matched=verdict.matched,
                        date=date,
                        chat_id=chat_id,
                    )
                    confirmations.append((fact.content, verdict.matched))
                    continue
                except Exception as e:
                    logger.warning(
                        f"Confirmation sidecar write failed; logging the fact: {e}"
                    )
            elif verdict.is_revision and "revision" not in (fact.tags or []):
                fact.tags = list(fact.tags or []) + ["revision"]
            to_write.append(fact)

        if confirmations:
            logger.info(
                f"{len(confirmations)} fact(s) already on record; "
                f"recorded as confirmations rather than new rows"
            )
        return to_write, confirmations

    async def _recall_known_facts(
        self, turn_text: str, user_id: str, chat_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Facts already in memory that are close to this turn, nearest-first.

        Returns `[{"content", "durable"}]`. *durable* marks the rows that come from an
        append-only store — a vault page or a daily log — as opposed to a chat
        transcript or the generated `MEMORY.md`. Only a durable match can justify not
        writing a repeat to the log, because only there is the claim already recorded
        somewhere the write path is not about to record it.

        Best-effort: any failure returns [] and extraction runs exactly as it did
        before. Enriching the prompt must never be able to block a memory write.
        """
        query = turn_text[:KNOWN_FACTS_QUERY_CHARS]
        if not query.strip():
            return []
        try:
            results = await self.search_memories(
                query=query,
                limit=KNOWN_FACTS_LIMIT,
                user_id=user_id,
                chat_id=chat_id,
            )
        except Exception as e:
            logger.warning(f"Known-fact recall failed; extracting without it: {e}")
            return []

        facts: List[Dict[str, Any]] = []
        seen: set = set()
        for r in results:
            content = " ".join(str(r.get("content", "")).split())
            if not content:
                continue
            key = content.lower()
            if key in seen:
                continue
            seen.add(key)
            metadata = r.get("metadata") or {}
            facts.append(
                {
                    "content": content[:KNOWN_FACTS_MAX_CHARS],
                    "durable": metadata.get("source_type") in DURABLE_SOURCE_TYPES,
                }
            )
        return facts

    async def _write_facts_to_markdown(
        self, facts: List[ExtractedFact], chat_id: str
    ) -> Optional[str]:
        """Append extracted facts to the daily markdown log (append-only).

        Returns the date string (YYYY-MM-DD, UTC) the facts were written to, or
        None if the markdown store is unavailable. A failed write raises, so the
        extraction queue keeps the turns instead of skipping facts it never stored.
        """
        if not self.markdown_store:
            return None

        fact_dicts = [
            {
                "content": f.content,
                "category": f.category or "general",
                "importance": f.importance,
                "tags": f.tags,
                "evidence": f.evidence,
            }
            for f in facts
        ]
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await self.markdown_store.append_daily_log(
            chat_id=chat_id, facts=fact_dicts, date=date
        )
        return date

    @staticmethod
    def _capture_mode() -> str:
        from suzent.config import CONFIG

        return getattr(CONFIG, "memory_capture_mode", "shadow")

    async def _run_capture(
        self, content: str, known_facts: List[str]
    ) -> Optional[capture.GateResult]:
        """Typed capture and its gate. None when no extraction model is set."""
        client = self.llm_client
        if client is None:
            return None
        response = await client.extract_with_schema(
            prompt=capture.format_capture_prompt(content, known_facts),
            response_model=capture.CaptureResponse,
            system=capture.CAPTURE_SYSTEM_PROMPT,
            temperature=LLM_EXTRACTION_TEMPERATURE,
        )
        rejected = self.markdown_store.read_rejected() if self.markdown_store else []
        return capture.gate(
            response.facts, content, rejected=rejected, known=known_facts
        )

    async def _capture_facts(
        self, content: str, known_facts: List[str]
    ) -> List[ExtractedFact]:
        """Typed capture: what the gate keeps, as facts for the daily log.

        Raises when the model fails, like the legacy extractor, so the extraction
        queue keeps the turns and retries them.
        """
        result = await self._run_capture(content, known_facts)
        if result is None:
            return []
        if result.dropped:
            logger.info(
                f"Capture gate dropped {len(result.dropped)} candidate(s): "
                + ", ".join(code for code, _ in result.dropped)
            )
        stale_after = (
            datetime.now(timezone.utc) + timedelta(days=capture.DATED_STALE_DAYS)
        ).strftime("%Y-%m-%d")
        facts: List[ExtractedFact] = []
        for fact in result.kept:
            tags = capture.fact_tags(fact, stale_after)
            if fact.content in result.ungrounded:
                tags.append("ungrounded")
            facts.append(
                ExtractedFact(
                    content=fact.content,
                    category=fact.category,
                    importance=fact.importance,
                    tags=tags,
                    evidence=fact.evidence,
                )
            )
        return facts

    async def _shadow_capture(
        self,
        content: str,
        known_facts: List[str],
        legacy: List[ExtractedFact],
        chat_id: str,
    ) -> None:
        """Run typed capture beside the legacy extractor and log both. Never raises."""
        if not self.markdown_store:
            return
        try:
            result = await self._run_capture(content, known_facts)
        except Exception as e:
            logger.warning(f"Shadow capture failed: {e}")
            return
        if result is None:
            return
        self.markdown_store.append_capture_shadow(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "chat_id": chat_id,
                "legacy": [f.content for f in legacy],
                "kept": [f.model_dump() for f in result.kept],
                "dropped": [
                    {"code": code, **f.model_dump()} for code, f in result.dropped
                ],
                "ungrounded": result.ungrounded,
            }
        )

    async def _extract_facts_llm(
        self, content: str, known_facts: Optional[List[str]] = None
    ) -> List[ExtractedFact]:
        """
        Extract facts using LLM with Pydantic schema-based structured output.

        Uses LiteLLM's structured output feature to enforce the FactExtractionResponse
        schema, ensuring validated ExtractedFact models are returned.

        Args:
            content: The formatted conversation turn.
            known_facts: Facts already in memory, nearest-first, so the model can tell
                a repeat from an update. Omitted when retrieval is unavailable.

        Returns:
            List of ExtractedFact models
        """
        system_prompt = memory_context.FACT_EXTRACTION_SYSTEM_PROMPT
        user_prompt = memory_context.format_fact_extraction_user_prompt(
            content, known_facts
        )
        # Keep one client throughout an extraction if settings change mid-request.
        client = self.llm_client
        if client is None:
            return []
        extraction_model = self.llm_extraction_model or getattr(client, "model", None)
        logger.debug(f"Starting LLM fact extraction with model={extraction_model!r}")

        try:
            # Use schema-based extraction with Pydantic model
            # LiteLLM converts FactExtractionResponse to json_schema format
            extraction_result = await client.extract_with_schema(
                prompt=user_prompt,
                response_model=FactExtractionResponse,
                system=system_prompt,
                temperature=LLM_EXTRACTION_TEMPERATURE,
            )

            facts = extraction_result.facts

            # Ensure defaults for context fields if missing (should be handled by Pydantic defaults but safe to check)
            # No action needed as Pydantic model has defaults for these fields

            logger.info(f"LLM extracted {len(facts)} facts via schema")

            # Debug: Show detailed extracted facts
            for i, fact in enumerate(facts, 1):
                logger.debug(
                    f"Extracted Fact #{i}:\n"
                    f"  Content: {fact.content}\n"
                    f"  Category: {fact.category}\n"
                    f"  Importance: {fact.importance}\n"
                    f"  Tags: {fact.tags}\n"
                    f"  Context: intent={fact.context_user_intent}, outcome={fact.context_outcome}"
                )

            return facts

        except Exception as e:
            logger.warning(
                f"Schema-based extraction failed for model={extraction_model!r}, "
                f"trying fallback: {e}"
            )

            # Fallback to basic JSON extraction
            try:
                response = await client.extract_structured(
                    prompt=user_prompt,
                    system=system_prompt,
                    temperature=LLM_EXTRACTION_TEMPERATURE,
                )

                # Handle different return formats from extract_structured
                raw_facts = []
                if isinstance(response, list):
                    # LLM returned a list directly
                    raw_facts = response
                elif isinstance(response, dict):
                    # LLM returned a dict, look for "facts" key
                    raw_facts = response.get("facts", [])
                else:
                    logger.warning(
                        f"Unexpected response format in fallback extraction: {type(response)}"
                    )

                # Convert to Pydantic models with defaults
                facts = []
                for f in raw_facts:
                    # validation: ensure f is a dict
                    if not isinstance(f, dict):
                        continue

                    # Build conversation context if present
                    ctx_data = f.get("conversation_context")
                    conversation_context = None
                    if ctx_data and isinstance(ctx_data, dict):
                        conversation_context = ConversationContext(
                            user_intent=ctx_data.get(
                                "user_intent", "inferred from conversation"
                            ),
                            agent_actions_summary=ctx_data.get("agent_actions_summary"),
                            outcome=ctx_data.get(
                                "outcome", "extracted from conversation turn"
                            ),
                        )
                    else:
                        # Provide default context for new facts
                        conversation_context = ConversationContext()

                    facts.append(
                        ExtractedFact(
                            content=f.get("content", ""),
                            category=f.get("category"),
                            importance=f.get("importance", DEFAULT_IMPORTANCE),
                            tags=f.get("tags", []),
                            # Map flat context fields from potentially nested JSON or flat JSON
                            context_user_intent=conversation_context.user_intent
                            if conversation_context
                            else "inferred from conversation",
                            context_agent_actions_summary=conversation_context.agent_actions_summary
                            if conversation_context
                            else None,
                            context_outcome=conversation_context.outcome
                            if conversation_context
                            else "extracted from conversation turn",
                        )
                    )

                logger.info(f"LLM extracted {len(facts)} facts via fallback")
                return facts

            except Exception as fallback_error:
                # Raised, not swallowed: the caller keeps the turns queued and
                # retries them, instead of treating them as having held nothing.
                raise RuntimeError(
                    f"LLM fact extraction failed for model={extraction_model!r}: "
                    f"{fallback_error}"
                ) from fallback_error

    # ===== Utility Methods =====

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about user's memories."""
        try:
            total_count = await self.store.get_memory_count(user_id=user_id)

            return {"total_memories": total_count, "user_id": user_id}
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total_memories": 0, "user_id": user_id}
