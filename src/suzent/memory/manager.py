"""
Memory Manager - orchestrates core and archival memory operations.
"""

from typing import Dict, List, Any, Optional, Union
from datetime import datetime

from suzent.logger import get_logger
from suzent.llm import EmbeddingGenerator, LLMClient
from .lancedb_store import LanceDBMemoryStore
from . import memory_context
from .models import (
    ConversationTurn,
    ExtractedFact,
    ConversationContext,
    MemoryExtractionResult,
    FactExtractionResponse,
)

logger = get_logger(__name__)

# Memory system constants
DEFAULT_MEMORY_RETRIEVAL_LIMIT = 5
DEFAULT_MEMORY_SEARCH_LIMIT = 10
IMPORTANT_MEMORY_THRESHOLD = 0.7

# Heuristic extraction importance scores
DEFAULT_IMPORTANCE = 0.5

# Deduplication and extraction settings
DEDUPLICATION_SEARCH_LIMIT = 3
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.85
LLM_EXTRACTION_TEMPERATURE = 1.0


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
    ):
        """Initialize memory manager.

        Args:
            store: LanceDB store instance
            embedding_model: LiteLLM model identifier for embeddings
            embedding_dimension: Expected embedding dimension (0 = auto-detect)
            llm_for_extraction: LLM model for fact extraction (uses LLM if provided)
        """
        self.store = store
        self.embedding_gen = EmbeddingGenerator(
            model=embedding_model, dimension=embedding_dimension
        )
        self.llm_extraction_model = llm_for_extraction
        self.llm_client = (
            LLMClient(model=llm_for_extraction) if llm_for_extraction else None
        )
        logger.info(
            f"MemoryManager initialized with embedding model: {embedding_model}, extraction model: {llm_for_extraction}"
        )

    # ===== Core Memory Blocks (Always visible to agent) =====

    async def get_core_memory(
        self, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get all core memory blocks with defaults."""
        blocks = await self.store.get_all_memory_blocks(
            chat_id=chat_id, user_id=user_id
        )

        # Ensure default blocks exist
        default_blocks = {
            "persona": "You are Suzent, a helpful AI assistant with long-term memory.",
            "user": "No user information yet.",
            "facts": "No facts stored yet.",
            "context": "No current context.",
        }

        for label, default_content in default_blocks.items():
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
        """Update a specific core memory block."""
        try:
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
        Refresh the 'facts' core memory block by summarizing highly important archival memories.

        This condenses scattered archival memories into a high-density 'facts' block
        that is always visible to the agent.
        """
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

            # Filter for high importance only
            important_facts = [
                f"- {m['content']}"
                for m in memories
                if m.get("importance", 0) >= IMPORTANT_MEMORY_THRESHOLD
            ]

            if not important_facts:
                logger.debug("No important facts found for core memory refresh")
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

                # 3. Update Core Memory Block
                if summary:
                    stats = await self.get_memory_stats(user_id)
                    # Append stats to show freshness
                    final_content = f"{summary.strip()}\n\n(Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Total Memories: {stats['total_memories']})"

                    await self.update_memory_block(
                        label="facts", content=final_content, user_id=user_id
                    )
                    logger.info(
                        f"Refreshed core memory 'facts' block for user {user_id}"
                    )

        except Exception as e:
            logger.error(f"Failed to refresh core memory facts: {e}")

    async def format_core_memory_for_context(
        self, chat_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> str:
        """Format core memory as text for prompt injection."""
        try:
            blocks = await self.get_core_memory(chat_id=chat_id, user_id=user_id)
        except Exception as e:
            logger.error(f"Error getting core memory blocks: {e}")
            return ""

        return memory_context.format_core_memory_section(blocks)

    async def retrieve_relevant_memories(
        self,
        query: str,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = DEFAULT_MEMORY_RETRIEVAL_LIMIT,
    ) -> str:
        """
        Automatically retrieve and format relevant memories for a query.
        This is called before the agent processes the message to inject context.

        Args:
            query: User's input query
            chat_id: Optional chat context
            user_id: User identifier
            limit: Maximum number of memories to retrieve

        Returns:
            Formatted string with relevant memories, or empty string if none found
        """
        try:
            memories = await self.search_memories(
                query=query, limit=limit, chat_id=chat_id, user_id=user_id
            )

            if not memories:
                return ""

            # Format memories for context injection
            memory_context_str = memory_context.format_retrieved_memories_section(
                memories, tag_important=True
            )
            logger.info(f"Retrieved {len(memories)} relevant memories for query")
            return memory_context_str

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
        Uses hybrid search: semantic + full-text + importance ranking.
        """
        try:
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
            MemoryExtractionResult with extracted facts and memory IDs
        """
        result = MemoryExtractionResult.empty()
        high_importance_found = False

        try:
            # Convert dict to Pydantic model if needed
            if isinstance(conversation_turn, dict):
                turn = ConversationTurn.from_dict(conversation_turn)
            else:
                turn = conversation_turn

            # Format the full turn into a text representation for the LLM
            turn_text = turn.format_for_extraction()

            # Extract facts using the formatted text
            extracted_facts = await self._extract_facts_llm(turn_text)

            if not extracted_facts:
                logger.debug("No facts extracted from conversation turn")
                return result

            logger.debug(
                f"Extracted {len(extracted_facts)} facts: {[f.content for f in extracted_facts]}"
            )

            result.extracted_facts = [f.content for f in extracted_facts]

            # Store memories
            await self._deduplicate_and_store_facts(
                extracted_facts, user_id, chat_id, result
            )

            # Check for high importance facts to trigger core memory update
            for fact in extracted_facts:
                if fact.importance >= IMPORTANT_MEMORY_THRESHOLD:
                    high_importance_found = True
                    break

            logger.info(
                f"Processed conversation turn: created {len(result.memories_created)} memories"
            )

            # Trigger core memory refresh if needed (fire and forget handled by caller/event loop in theory,
            # here we await it but log errors so it doesn't fail the request)
            if high_importance_found:
                # We could make this async in background, but for now just await safely
                logger.info(
                    "High importance fact found, triggering core memory refresh"
                )
                try:
                    await self.refresh_core_memory_facts(user_id)
                except Exception as e:
                    logger.error(f"Background core memory refresh failed: {e}")

        except Exception as e:
            logger.error(f"Failed to process conversation turn for memories: {e}")
            import traceback

            logger.error(traceback.format_exc())

        return result

    async def _deduplicate_and_store_facts(
        self,
        facts: List[ExtractedFact],
        user_id: str,
        source_chat_id: str,
        result: MemoryExtractionResult,
    ):
        """Helper to deduplicate and store a list of facts."""
        for fact in facts:
            # Metadata construction
            metadata = {
                "importance": fact.importance,
                "category": fact.category,
                "tags": fact.tags,
                "source_chat_id": source_chat_id,
            }
            if fact.conversation_context:
                metadata["conversation_context"] = (
                    fact.conversation_context.model_dump()
                )

            # Search for similar existing memories
            similar = await self.search_memories(
                query=fact.content,
                limit=DEDUPLICATION_SEARCH_LIMIT,
                user_id=user_id,
                chat_id=None,  # User-level memories
                use_hybrid=False,
            )

            if (
                similar
                and similar[0].get("similarity", 0) > DEDUPLICATION_SIMILARITY_THRESHOLD
            ):
                # Very similar memory exists - update/skip
                result.memories_updated.append(str(similar[0]["id"]))
            else:
                # New fact - store it
                memory_id = await self._add_memory_internal(
                    content=fact.content,
                    metadata=metadata,
                    chat_id=None,  # User-level memory
                    user_id=user_id,
                )
                result.memories_created.append(memory_id)

    async def process_message_for_memories(
        self, message: Dict[str, Any], chat_id: str, user_id: str
    ) -> MemoryExtractionResult:
        """
        (Legacy) Automatically extract and store important facts from a single message.
        kept for backward compatibility or direct calls.
        """
        result = MemoryExtractionResult.empty()

        try:
            # Extract facts from message
            facts = await self._extract_facts_simple(message)

            if not facts:
                return result

            result.extracted_facts = [f.content for f in facts]

            # Use shared storage logic
            await self._deduplicate_and_store_facts(facts, user_id, chat_id, result)

            logger.info(
                f"Processed message: created {len(result.memories_created)} memories"
            )

        except Exception as e:
            logger.error(f"Failed to process message for memories: {e}")

        return result

    async def _extract_facts_simple(
        self, message: Dict[str, Any]
    ) -> List[ExtractedFact]:
        """
        Extract facts from a message.
        Uses LLM if available
        """
        content = message.get("content", "")
        role = message.get("role", "")

        # Only extract from user messages
        if role != "user":
            return []

        # Use LLM-based extraction if configured
        if self.llm_client:
            return await self._extract_facts_llm(content)
        else:
            return []

    async def _extract_facts_llm(self, content: str) -> List[ExtractedFact]:
        """
        Extract facts using LLM with Pydantic schema-based structured output.

        Uses LiteLLM's structured output feature to enforce the FactExtractionResponse
        schema, ensuring validated ExtractedFact models are returned.

        Returns:
            List of ExtractedFact models
        """
        system_prompt = memory_context.FACT_EXTRACTION_SYSTEM_PROMPT
        user_prompt = memory_context.format_fact_extraction_user_prompt(content)

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

            # Ensure all facts have conversation_context set
            for fact in facts:
                if fact.conversation_context is None:
                    fact.conversation_context = ConversationContext()

            logger.info(f"LLM extracted {len(facts)} facts via schema")

            # Debug: Show detailed extracted facts
            for i, fact in enumerate(facts, 1):
                logger.debug(
                    f"Extracted Fact #{i}:\n"
                    f"  Content: {fact.content}\n"
                    f"  Category: {fact.category}\n"
                    f"  Importance: {fact.importance}\n"
                    f"  Tags: {fact.tags}\n"
                    f"  Context: intent={fact.conversation_context.user_intent if fact.conversation_context else 'N/A'}, "
                    f"outcome={fact.conversation_context.outcome if fact.conversation_context else 'N/A'}"
                )

            return facts

        except Exception as e:
            logger.warning(f"Schema-based extraction failed, trying fallback: {e}")

            # Fallback to basic JSON extraction
            try:
                response = await self.llm_client.extract_structured(
                    prompt=user_prompt,
                    system=system_prompt,
                    temperature=LLM_EXTRACTION_TEMPERATURE,
                )

                raw_facts = response.get("facts", [])

                # Convert to Pydantic models with defaults
                facts = []
                for f in raw_facts:
                    # Build conversation context if present
                    ctx_data = f.get("conversation_context")
                    conversation_context = None
                    if ctx_data:
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
                            conversation_context=conversation_context,
                        )
                    )

                logger.info(f"LLM extracted {len(facts)} facts via fallback")
                return facts

            except Exception as fallback_error:
                logger.error(f"LLM fact extraction failed completely: {fallback_error}")
                return []

    async def _add_memory_internal(
        self,
        content: str,
        metadata: Dict[str, Any],
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Internal method to add memory to archival storage."""
        try:
            # Generate embedding
            embedding = await self.embedding_gen.generate(content)

            # Store in database
            memory_id = await self.store.add_memory(
                content=content,
                embedding=embedding,
                user_id=user_id,
                chat_id=chat_id,
                metadata=metadata,
                importance=metadata.get("importance", DEFAULT_IMPORTANCE),
            )

            return memory_id

        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            raise

    # ===== Utility Methods =====

    async def get_memory_stats(self, user_id: str) -> Dict[str, Any]:
        """Get statistics about user's memories."""
        try:
            total_count = await self.store.get_memory_count(user_id=user_id)

            return {"total_memories": total_count, "user_id": user_id}
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total_memories": 0, "user_id": user_id}
