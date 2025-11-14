"""
Memory Manager - orchestrates core and archival memory operations.
"""

from typing import Dict, List, Any, Optional
import json

from suzent.logger import get_logger
from suzent.llm import EmbeddingGenerator, LLMClient
from .postgres_store import PostgresMemoryStore
from . import memory_context

logger = get_logger(__name__)

# Memory system constants
DEFAULT_MEMORY_RETRIEVAL_LIMIT = 5
DEFAULT_MEMORY_SEARCH_LIMIT = 10
IMPORTANT_MEMORY_THRESHOLD = 0.7

# Heuristic extraction importance scores
DEFAULT_IMPORTANCE = 0.5

# Deduplication and extraction settings
DEDUPLICATION_SEARCH_LIMIT = 3
DEDUPLICATION_SIMILARITY_THRESHOLD = 0.9
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
        store: PostgresMemoryStore,
        embedding_model: str = None,
        embedding_dimension: int = 0,
        llm_for_extraction: Optional[str] = None
    ):
        """Initialize memory manager.
        
        Args:
            store: PostgreSQL store instance
            embedding_model: LiteLLM model identifier for embeddings
            embedding_dimension: Expected embedding dimension (0 = auto-detect)
            llm_for_extraction: LLM model for fact extraction (uses LLM if provided)
        """
        self.store = store
        self.embedding_gen = EmbeddingGenerator(
            model=embedding_model,
            dimension=embedding_dimension
        )
        self.llm_extraction_model = llm_for_extraction
        self.llm_client = LLMClient(model=llm_for_extraction) if llm_for_extraction else None
        logger.info(f"MemoryManager initialized with embedding model: {embedding_model}, extraction model: {llm_for_extraction}")

    # ===== Core Memory Blocks (Always visible to agent) =====

    async def get_core_memory(
        self,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Get all core memory blocks with defaults."""
        blocks = await self.store.get_all_memory_blocks(chat_id=chat_id, user_id=user_id)

        # Ensure default blocks exist
        default_blocks = {
            'persona': 'You are Suzent, a helpful AI assistant with long-term memory.',
            'user': 'No user information yet.',
            'facts': 'No facts stored yet.',
            'context': 'No current context.'
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
        user_id: Optional[str] = None
    ) -> bool:
        """Update a specific core memory block."""
        try:
            await self.store.set_memory_block(
                label=label,
                content=content,
                chat_id=chat_id,
                user_id=user_id
            )
            logger.info(f"Updated core memory block '{label}' for user={user_id}, chat={chat_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update memory block '{label}': {e}")
            return False

    async def format_core_memory_for_context(
        self,
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None
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
        limit: int = DEFAULT_MEMORY_RETRIEVAL_LIMIT
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
                query=query,
                limit=limit,
                chat_id=chat_id,
                user_id=user_id
            )
            
            if not memories:
                return ""
            
            # Format memories for context injection
            memory_context_str = memory_context.format_retrieved_memories_section(
                memories,
                tag_important=True
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
        use_hybrid: bool = True
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
                    limit=limit
                )
            else:
                # Pure semantic search
                results = await self.store.semantic_search(
                    query_embedding=query_embedding,
                    user_id=user_id,
                    chat_id=chat_id,
                    limit=limit
                )

            logger.info(f"Memory search for '{query}': found {len(results)} results")
            return results

        except Exception as e:
            import traceback
            logger.error(f"Memory search failed: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            return []

    # ===== Automatic Memory Management (Internal) =====

    async def process_message_for_memories(
        self,
        message: Dict[str, Any],
        chat_id: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Automatically extract and store important facts from a message.
        Called after each user message or assistant response.

        Returns: {
            "extracted_facts": List[str],
            "memories_created": List[str],  # memory IDs
            "memories_updated": List[str],
            "conflicts_detected": List[Dict]
        }
        """
        result = {
            "extracted_facts": [],
            "memories_created": [],
            "memories_updated": [],
            "conflicts_detected": []
        }

        try:
            # Extract facts from message (simplified for POC)
            facts = await self._extract_facts_simple(message)

            if not facts:
                return result

            result["extracted_facts"] = [f["content"] for f in facts]

            # For each fact, check if it already exists
            for fact in facts:
                # Search for similar existing memories
                similar = await self.search_memories(
                    query=fact["content"],
                    limit=DEDUPLICATION_SEARCH_LIMIT,
                    user_id=user_id,
                    chat_id=None  # Search user-level memories
                )

                if similar and similar[0].get('similarity', 0) > DEDUPLICATION_SIMILARITY_THRESHOLD:
                    # Very similar memory exists - skip
                    result["memories_updated"].append(str(similar[0]['id']))
                else:
                    # New fact - store it
                    memory_id = await self._add_memory_internal(
                        content=fact["content"],
                        metadata={
                            "importance": fact.get("importance", DEFAULT_IMPORTANCE),
                            "category": fact.get("category"),
                            "tags": fact.get("tags", []),
                            "source_chat_id": chat_id,
                        },
                        chat_id=None,  # User-level memory
                        user_id=user_id
                    )
                    result["memories_created"].append(memory_id)

            logger.info(f"Processed message: created {len(result['memories_created'])} memories")

        except Exception as e:
            logger.error(f"Failed to process message for memories: {e}")

        return result

    async def _extract_facts_simple(
        self,
        message: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
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

    async def _extract_facts_llm(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract facts using LLM with structured output.
        
        Returns list of facts with category, importance, and tags.
        """
        system_prompt = memory_context.FACT_EXTRACTION_SYSTEM_PROMPT
        user_prompt = memory_context.format_fact_extraction_user_prompt(content)

        try:
            response = await self.llm_client.extract_structured(
                prompt=user_prompt,
                system=system_prompt,
                temperature=LLM_EXTRACTION_TEMPERATURE
            )

            facts = response.get("facts", [])
            logger.info(f"LLM extracted {len(facts)} facts from message")
            return facts

        except Exception as e:
            logger.error(f"LLM fact extraction failed")
            return []

    async def _add_memory_internal(
        self,
        content: str,
        metadata: Dict[str, Any],
        chat_id: Optional[str] = None,
        user_id: Optional[str] = None
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
                importance=metadata.get("importance", DEFAULT_IMPORTANCE)
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

            return {
                "total_memories": total_count,
                "user_id": user_id
            }
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"total_memories": 0, "user_id": user_id}
