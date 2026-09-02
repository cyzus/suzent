"""
Memory Manager - orchestrates core and archival memory operations.
"""

from typing import Dict, List, Any, Optional, Union, TYPE_CHECKING
from datetime import datetime, timezone

from suzent.logger import get_logger
from suzent.llm import EmbeddingGenerator, LLMClient
from .lancedb_store import LanceDBMemoryStore
from .markdown_store import MarkdownMemoryStore
from .indexer import CoreMemoryFileIndexer
from .classifier import classify_fact
from . import memory_context
from .models import (
    ConversationTurn,
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
IMPORTANT_MEMORY_THRESHOLD = 0.7

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
        # (chat_id, user_id, sandbox_enabled) -> (revision, rendered section).
        # Bounded by the number of live chats; entries are tiny strings.
        self._core_memory_cache: Dict[tuple, tuple] = {}
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
                    # MEMORY.md — a person editing this block is the highest-quality
                    # signal the system gets, so it goes to the zone that generators
                    # never touch, stamped with a `human:` actor.
                    await self.markdown_store.write_memory_manual_zone(
                        content, actor=f"human:{user_id or 'unknown'}"
                    )
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

    async def refresh_core_memory_facts(self, user_id: str):
        """
        Refresh the 'facts' core memory block by summarizing top archival memories.

        Legacy path, kept only until the vault has enough consolidated personal pages
        for `promote_memory_md` to take over — which is why it stands down as soon as
        those pages exist rather than racing the dream for the same file.
        """
        if await self._vault_owns_memory_file():
            logger.debug("Vault has personal pages; leaving MEMORY.md to the dream")
            return

        try:
            # 1. Fetch top important memories
            # We use list_memories instead of search to get global top facts for user
            memories = await self.store.list_memories(
                user_id=user_id,
                limit=50,  # Fetch enough to summarize
                order_by="importance",
                order_desc=True,
            )

            if not memories:
                return

            # The rows are already the top 50 by importance, and that is as much
            # selectivity as the column can offer: the indexer stamps every row it
            # writes with a constant 0.5, so an additional
            # `>= IMPORTANT_MEMORY_THRESHOLD` cut here matched nothing except the
            # pre-June legacy rows — quietly rebuilding MEMORY.md from data months
            # out of date, and set to produce an empty file the moment those rows
            # are retired. Rank, then take what we get.
            important_facts = [
                f"- {m['content']}" for m in memories if m.get("content", "").strip()
            ]

            if not important_facts:
                logger.debug("No facts available for core memory refresh")
                return

            facts_list_text = "\n".join(important_facts)

            # 2. Summarize with LLM
            if self.llm_client:
                summary = await self.llm_client.complete(
                    prompt=memory_context.CORE_MEMORY_SUMMARIZATION_PROMPT.format(
                        facts_list=facts_list_text
                    ),
                    temperature=0.3,  # Low temp for factual summary
                    max_tokens=1000,
                )

                # 3. Write summary to MEMORY.md (file-based SSoT). The store stamps
                #    the file itself, in UTC; this used to add a second stamp from a
                #    naive `datetime.now()`, so every generated file carried two
                #    timestamps an hour apart wherever local time is not UTC.
                if summary:
                    stats = await self.get_memory_stats(user_id)
                    final_content = (
                        f"{summary.strip()}\n\n_{stats['total_memories']} memories._"
                    )

                    if self.markdown_store:
                        try:
                            await self.markdown_store.write_memory_file(final_content)
                        except Exception as md_err:
                            logger.warning(f"Failed to write MEMORY.md: {md_err}")

                    logger.info(
                        f"Refreshed core memory 'facts' block for user {user_id}"
                    )

        except Exception as e:
            logger.error(f"Failed to refresh core memory facts: {e}")

    async def _vault_owns_memory_file(self) -> bool:
        """True once `promote_memory_md` has real material to work from.

        Both writers regenerate the same file, and the newer one is strictly better
        informed — it reads consolidated pages rather than raw extractions. Handing
        over on the first personal page means the transition needs no flag day and no
        config: as the dream fills the vault, the legacy path simply stops firing.
        """
        if not self.markdown_store:
            return False
        try:
            personal_dir = self.markdown_store.notebook_dir / "3_Personal"
            return any(personal_dir.rglob("*.md"))
        except Exception:
            return False

    async def promote_memory_md(self, user_id: str) -> None:
        """Regenerate the always-visible MEMORY.md from the vault's personal facts +
        recall signal. Deterministic single LLM call, run by the dream runner after a
        productive consolidation (replaces refresh_core_memory_facts; plan C1).
        """
        if not self.markdown_store or not self.llm_client:
            return
        try:
            from suzent.config import CONFIG

            personal_dir = self.markdown_store.notebook_dir / "3_Personal"
            chunks: List[str] = []
            if personal_dir.exists():
                for p in sorted(personal_dir.rglob("*.md")):
                    try:
                        chunks.append(p.read_text(encoding="utf-8"))
                    except Exception:
                        continue
            personal_facts = "\n\n".join(chunks).strip()
            if not personal_facts:
                return

            recalls = self.markdown_store.read_recalls()
            snippets = [r.get("snippet", "") for r in recalls if r.get("snippet")]
            recall_summary = "\n".join(f"- {s}" for s in snippets[-30:]) or "(none)"

            max_lines = getattr(CONFIG, "memory_consolidation_memory_max_lines", 200)
            summary = await self.llm_client.complete(
                prompt=memory_context.MEMORY_PROMOTION_PROMPT.format(
                    personal_facts=personal_facts[:12000],
                    recall_summary=recall_summary,
                    max_lines=max_lines,
                ),
                temperature=0.3,
                max_tokens=2000,
            )
            if summary:
                await self.markdown_store.write_memory_file(summary.strip())
                logger.info("Promoted MEMORY.md from consolidated personal facts")
        except Exception as e:
            logger.error(f"promote_memory_md failed: {e}")

    async def format_core_memory_for_context(
        self,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        sandbox_enabled: bool = True,
        path_resolver=None,
    ) -> str:
        """Format core memory as text for prompt injection."""
        try:
            blocks = await self.get_core_memory(chat_id=chat_id, user_id=user_id)
        except Exception as e:
            logger.error(f"Error getting core memory blocks: {e}")
            return ""

        shared_path = None
        mount_notebook = None
        project_context_path = "/workspace/context.md" if sandbox_enabled else None
        if not sandbox_enabled and path_resolver is not None:
            shared_path = str(path_resolver.sandbox_data_path / "shared").replace(
                "\\", "/"
            )
            mount_notebook = (
                str(path_resolver.custom_mounts.get("/mnt/notebook", "")).replace(
                    "\\", "/"
                )
                or None
            )
            project_context_path = str(
                path_resolver.get_working_dir() / "context.md"
            ).replace("\\", "/")

        return memory_context.format_core_memory_section(
            blocks,
            sandbox_enabled=sandbox_enabled,
            chat_id=chat_id,
            shared_path=shared_path,
            mount_notebook=mount_notebook,
            project_context_path=project_context_path,
        )

    async def get_core_memory_context(
        self,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        sandbox_enabled: bool = True,
        path_resolver=None,
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
            )

        key = (chat_id, user_id, sandbox_enabled)
        try:
            revision = store.core_memory_revision(chat_id)
        except Exception as e:
            logger.debug(f"Core memory revision unavailable, rebuilding: {e}")
            revision = None

        if revision is not None:
            cached = self._core_memory_cache.get(key)
            if cached is not None and cached[0] == revision:
                return cached[1]

        rendered = await self.format_core_memory_for_context(
            chat_id=chat_id,
            user_id=user_id,
            sandbox_enabled=sandbox_enabled,
            path_resolver=path_resolver,
        )
        if revision is not None:
            self._core_memory_cache[key] = (revision, rendered)
        return rendered

    def _log_recalls(self, memories: List[Dict[str, Any]]) -> None:
        """Record retrieved memories to the recall log (usage signal for MEMORY.md
        promotion). Best-effort — never raises."""
        if not self.markdown_store or not memories:
            return
        try:
            for m in memories:
                if not isinstance(m, dict):
                    continue
                meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
                self.markdown_store.append_recall(
                    m.get("content", ""), (meta or {}).get("source_type", "")
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

    async def process_conversation_turn_for_memories(
        self,
        conversation_turn: Union[ConversationTurn, Dict[str, Any]],
        chat_id: str,
        user_id: str,
    ) -> MemoryExtractionResult:
        """
        Automatically extract and store important facts from a conversation turn.
        Called after the assistant response is complete.

        Args:
            conversation_turn: ConversationTurn model or dict with same structure
            chat_id: Chat identifier
            user_id: User identifier

        Returns:
            MemoryExtractionResult with the list of extracted fact contents.

        Append-only write path (fixes #34): facts are written to the markdown daily
        log (the source of truth) and indexed into LanceDB. There is still NO
        write-time deduplication — an update to a fact must never be silently
        dropped, which is what #34 was. Repetition is suppressed one step earlier
        instead, by showing the extractor what memory already holds so a re-mention
        is not extracted at all. What survives that is resolved by the dream
        consolidation pass. See docs/02-concepts/memory/consolidation.md and
        docs/03-developing/memory/deduplication.md.
        """
        result = MemoryExtractionResult.empty()

        try:
            # Convert dict to Pydantic model if needed
            if isinstance(conversation_turn, dict):
                turn = ConversationTurn.from_dict(conversation_turn)
            else:
                turn = conversation_turn

            # Extract facts from the formatted turn, showing the model what memory
            # already holds so a re-mention is not stored as a new fact.
            turn_text = turn.format_for_extraction()
            known = await self._recall_known_facts(turn_text, user_id, chat_id)
            # Only the durable ones. The prompt tells the model not to re-extract what
            # it is shown, and a fact that exists solely in a transcript or in the
            # generated MEMORY.md is not recorded anywhere the write path is about to
            # record it -- suppressing it there means it never reaches the append-only
            # log at all, and `_split_confirmations` cannot recover a fact the model
            # already declined to emit.
            extracted_facts = await self._extract_facts_llm(
                turn_text, [k["content"] for k in known if k.get("durable")]
            )

            if not extracted_facts:
                logger.debug("No facts extracted from conversation turn")
                return result

            # Separate out the re-statements. What is left keeps the append-only path.
            extracted_facts, confirmations = await self._split_confirmations(
                extracted_facts, known, chat_id
            )
            result.confirmed_facts = [c[0] for c in confirmations]

            if not extracted_facts:
                logger.debug(
                    f"Turn held only re-statements: {len(confirmations)} confirmed"
                )
                return result

            result.extracted_facts = [f.content for f in extracted_facts]
            logger.debug(
                f"Extracted {len(extracted_facts)} facts: {result.extracted_facts}"
            )

            # 1. Append to the markdown daily log (append-only source of truth).
            date = await self._write_facts_to_markdown(extracted_facts, chat_id)

            # 2. Index the day's log into LanceDB (the derived search index). The
            #    indexer is the only writer to LanceDB (mutation invariant).
            if date and self.markdown_store:
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

            # 3. Keep MEMORY.md fresh from the top archival facts. Retained until the
            #    dream's promote_memory_md replaces it (see plan, finding C1).
            if any(f.importance >= IMPORTANT_MEMORY_THRESHOLD for f in extracted_facts):
                try:
                    await self.refresh_core_memory_facts(user_id)
                except Exception as e:
                    logger.error(f"Core memory refresh failed: {e}")

            logger.info(
                f"Processed conversation turn: extracted {len(result.extracted_facts)} facts"
            )

        except Exception as e:
            logger.error(f"Failed to process conversation turn for memories: {e}")
            import traceback

            logger.error(traceback.format_exc())

        return result

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
        None if the markdown store is unavailable or the write failed.
        """
        if not self.markdown_store:
            return None

        try:
            fact_dicts = [
                {
                    "content": f.content,
                    "category": f.category or "general",
                    "importance": f.importance,
                    "tags": f.tags,
                    "context": {
                        "user_intent": f.context_user_intent,
                        "agent_actions_summary": f.context_agent_actions_summary,
                        "outcome": f.context_outcome,
                    },
                }
                for f in facts
            ]
            from datetime import timezone

            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            await self.markdown_store.append_daily_log(
                chat_id=chat_id, facts=fact_dicts, date=date
            )
            return date
        except Exception as e:
            # Markdown write failure should not block the main flow
            logger.warning(f"Failed to write facts to markdown daily log: {e}")
            return None

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
        extraction_model = self.llm_extraction_model or getattr(
            self.llm_client, "model", None
        )
        logger.debug(f"Starting LLM fact extraction with model={extraction_model!r}")

        try:
            # Use schema-based extraction with Pydantic model
            # LiteLLM converts FactExtractionResponse to json_schema format
            extraction_result = await self.llm_client.extract_with_schema(
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
                response = await self.llm_client.extract_structured(
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
                logger.error(
                    f"LLM fact extraction failed completely for model={extraction_model!r}: "
                    f"{fallback_error}"
                )
                return []

    # ===== Utility Methods =====

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about user's memories."""
        try:
            total_count = await self.store.get_memory_count(user_id=user_id)

            return {"total_memories": total_count, "user_id": user_id}
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total_memories": 0, "user_id": user_id}
