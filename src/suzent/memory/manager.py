"""
Memory Manager - orchestrates core and archival memory operations.
"""

from typing import Dict, List, Any, Optional
import json

from suzent.logger import get_logger
from suzent.llm import EmbeddingGenerator, LLMClient
from .postgres_store import PostgresMemoryStore

logger = get_logger(__name__)

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
            llm_for_extraction: LLM model for fact extraction (uses LLM if provided, else heuristics)
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

        memory_section = f"""
## Your Memory System

You have access to a two-tier memory system:

### Core Memory (Always Visible)
This is your active working memory. You can edit these blocks using the `memory_block_update` tool.

**Persona** (your identity and capabilities):
{blocks.get('persona', 'Not set')}

**User** (information about the current user):
{blocks.get('user', 'Not set')}

**Facts** (key facts you should always remember):
{blocks.get('facts', 'Not set')}

**Context** (current session context):
{blocks.get('context', 'Not set')}

### Archival Memory (Search When Needed)
You have unlimited long-term memory storage that is automatically managed. Use `memory_search` to find relevant past information when needed.

**Memory Guidelines:**
- Update your core memory blocks when you learn important new information about yourself or the user
- Search your archival memory before asking the user for information they may have already provided
- Memories are automatically stored as you interact—you don't need to explicitly save them
"""
        return memory_section

    # ===== Archival Memory Search (Agent-facing) =====

    async def search_memories(
        self,
        query: str,
        limit: int = 10,
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
                    limit=3,
                    user_id=user_id,
                    chat_id=None  # Search user-level memories
                )

                if similar and similar[0].get('similarity', 0) > 0.9:
                    # Very similar memory exists - skip
                    result["memories_updated"].append(str(similar[0]['id']))
                else:
                    # New fact - store it
                    memory_id = await self._add_memory_internal(
                        content=fact["content"],
                        metadata={
                            "importance": fact.get("importance", 0.5),
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
        Uses LLM if available, otherwise falls back to simple heuristics.
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
            return await self._extract_facts_heuristic(content)

    async def _extract_facts_llm(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract facts using LLM with structured output.
        
        Returns list of facts with category, importance, and tags.
        """
        system_prompt = """You are a fact extraction system. Extract memorable facts from user messages.

Focus on extracting:
- Personal information (name, location, job, etc.)
- Preferences (likes, dislikes, favorites)
- Goals and intentions (plans, desires, tasks)
- Important context (relationships, events, experiences)
- Technical details (tools they use, skills they have)

For each fact, provide:
- content: The fact as a clear, standalone statement
- category: One of [personal, preference, goal, context, technical, other]
- importance: Float 0.0-1.0 (0.8-1.0 = critical, 0.5-0.8 = important, 0.0-0.5 = minor)
- tags: List of relevant tags

Return JSON in this format:
{
  "facts": [
    {
      "content": "User prefers dark mode",
      "category": "preference",
      "importance": 0.7,
      "tags": ["preference", "ui"]
    }
  ]
}

If no facts are worth extracting, return {"facts": []}.
"""

        user_prompt = f"""Extract facts from this message:

{content}

Remember: Only extract facts that are worth remembering long-term. Skip questions, greetings, and ephemeral content."""

        try:
            response = await self.llm_client.extract_structured(
                prompt=user_prompt,
                system=system_prompt,
                temperature=0.3
            )

            facts = response.get("facts", [])
            logger.info(f"LLM extracted {len(facts)} facts from message")
            return facts

        except Exception as e:
            logger.error(f"LLM fact extraction failed, falling back to heuristics: {e}")
            return await self._extract_facts_heuristic(content)

    async def _extract_facts_heuristic(self, content: str) -> List[Dict[str, Any]]:
        """
        Fallback heuristic-based fact extraction.
        Simple pattern matching for basic fact types.
        """
        facts = []

        # Look for preference patterns
        if any(word in content.lower() for word in ["i love", "i like", "i prefer", "my favorite"]):
            facts.append({
                "content": content,
                "category": "preference",
                "importance": 0.7,
                "tags": ["preference", "user_info"]
            })

        # Look for personal information
        elif any(word in content.lower() for word in ["i am", "my name is", "i work as", "i live in"]):
            facts.append({
                "content": content,
                "category": "personal",
                "importance": 0.8,
                "tags": ["personal", "user_info"]
            })

        # Look for goals/tasks
        elif any(word in content.lower() for word in ["i want to", "i need to", "my goal", "i'm working on"]):
            facts.append({
                "content": content,
                "category": "goal",
                "importance": 0.6,
                "tags": ["goal", "task"]
            })

        return facts

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
                importance=metadata.get("importance", 0.5)
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
