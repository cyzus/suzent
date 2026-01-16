"""
Memory tools exposed to agents.
"""

from smolagents import Tool
from datetime import datetime

from suzent.logger import get_logger
from suzent.config import CONFIG
from .manager import MemoryManager

logger = get_logger(__name__)


class MemorySearchTool(Tool):
    """
    Search long-term archival memory for relevant information.
    """

    name = "memory_search"
    description = """Search your long-term archival memory for relevant information.

Use this to recall facts, preferences, or information you learned in past conversations.
The search uses semantic similarity to find relevant memories even if the exact words differ.

Args:
    query: What to search for in memory (use natural language)
    limit: Maximum number of results to return (default: 10)

Returns:
    Formatted list of relevant memories with metadata
"""

    inputs = {
        "query": {
            "type": "string",
            "description": "What to search for in memory (use natural language)",
        },
        "limit": {
            "type": "number",
            "description": "Maximum number of results to return (default: 10)",
            "nullable": True,
        },
    }

    output_type = "string"

    def __init__(self, memory_manager: MemoryManager):
        super().__init__()
        self.memory_manager = memory_manager
        self._user_id = CONFIG.user_id
        self._chat_id = None
        # Main event loop reference will be injected by agent_manager
        self._main_loop = None

    def set_context(self, chat_id: str = None, user_id: str = "default"):
        """Set chat and user context for this tool instance."""
        self._chat_id = chat_id
        self._user_id = user_id

    async def forward_async(self, query: str, limit: int = 10) -> str:
        """Execute memory search."""
        try:
            # Get user_id from context (would come from agent context in real implementation)
            user_id = getattr(self, "_user_id", CONFIG.user_id)
            # chat_id = getattr(self, '_chat_id', None)

            memories = await self.memory_manager.search_memories(
                query=query,
                limit=limit,
                chat_id=None,  # Always search user-level memories
                user_id=user_id,
            )

            if not memories:
                return "No relevant memories found."

            # Format results for agent
            formatted = ["Found relevant memories:\n"]
            for i, mem in enumerate(memories, 1):
                # Handle datetime formatting
                created_at = mem.get("created_at")
                if isinstance(created_at, datetime):
                    date_str = created_at.strftime("%Y-%m-%d")
                else:
                    date_str = str(created_at)[:10] if created_at else "Unknown"

                # Parse metadata
                metadata = mem.get("metadata", {})
                if isinstance(metadata, str):
                    import json

                    try:
                        metadata = json.loads(metadata)
                    except json.JSONDecodeError:
                        metadata = {}

                tags = metadata.get("tags", [])
                tag_str = f" [Tags: {', '.join(tags)}]" if tags else ""

                similarity = mem.get("similarity", mem.get("semantic_score", 0))

                formatted.append(
                    f"{i}. {mem['content']}\n"
                    f"   (Stored: {date_str}, Relevance: {similarity:.2f}, Importance: {mem['importance']:.2f}{tag_str})"
                )

            result = "\n\n".join(formatted)
            logger.info(
                f"Memory search returned {len(memories)} results for query: {query}"
            )
            return result

        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return f"Error searching memories: {str(e)}"

    def forward(self, query: str, limit: int = 10) -> str:
        """Synchronous wrapper for async forward - runs in main event loop."""
        import asyncio

        # If we have a reference to the main loop, use it (thread-safe)
        if self._main_loop and self._main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.forward_async(query, limit), self._main_loop
            )
            return future.result(timeout=30)  # 30 second timeout

        # Fallback: run in new loop (for testing/standalone use)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.forward_async(query, limit))
        finally:
            loop.close()
            asyncio.set_event_loop(None)


class MemoryBlockUpdateTool(Tool):
    """
    Update core memory blocks that are always visible in context.
    """

    name = "memory_block_update"
    description = """Update your core memory blocks that are always visible in your context.

Core memory blocks:
- **persona**: Your identity, role, capabilities, and preferences
- **user**: Information about the current user (name, preferences, context)
- **facts**: Key facts you should always remember
- **context**: Current session context (active tasks, goals, constraints)

Use this to maintain up-to-date information in your "working memory" that you need
to reference frequently without searching.

Args:
    block: Which block to update ('persona', 'user', 'facts', or 'context')
    operation: Operation to perform ('replace', 'append', or 'search_replace')
    content: New content or content to append
    search_pattern: For search_replace: the text pattern to find and replace (optional)

Returns:
    Success or error message
"""

    inputs = {
        "block": {
            "type": "string",
            "description": "Which block to update: 'persona', 'user', 'facts', or 'context'",
        },
        "operation": {
            "type": "string",
            "description": "Operation: 'replace' (full rewrite), 'append' (add to end), or 'search_replace' (find and replace)",
        },
        "content": {
            "type": "string",
            "description": "New content or content to append",
        },
        "search_pattern": {
            "type": "string",
            "description": "For search_replace operation: the text pattern to find and replace",
            "nullable": True,
        },
    }

    output_type = "string"

    def __init__(self, memory_manager: MemoryManager):
        super().__init__()
        self.memory_manager = memory_manager
        self._user_id = CONFIG.user_id
        self._chat_id = None
        # Main event loop reference will be injected by agent_manager
        self._main_loop = None

    def set_context(self, chat_id: str = None, user_id: str = "default"):
        """Set chat and user context for this tool instance."""
        self._chat_id = chat_id
        self._user_id = user_id

    async def forward_async(
        self, block: str, operation: str, content: str, search_pattern: str = None
    ) -> str:
        """Execute memory block update."""
        try:
            # Validate block name
            valid_blocks = ["persona", "user", "facts", "context"]
            if block not in valid_blocks:
                return f"Error: Invalid block '{block}'. Must be one of: {', '.join(valid_blocks)}"

            # Get context
            user_id = getattr(self, "_user_id", CONFIG.user_id)
            chat_id = getattr(self, "_chat_id", None)

            # Decide scope: 'context' is chat-specific, others are user-level
            # This ensures persona/user/facts persist across all conversations
            update_chat_id = chat_id if block == "context" else None

            # Get current content (read from chat-specific or user-level)
            current_blocks = await self.memory_manager.get_core_memory(
                chat_id=chat_id,  # Read prioritizes chat-specific
                user_id=user_id,
            )
            current_content = current_blocks.get(block, "")

            # Perform operation
            if operation == "replace":
                new_content = content
            elif operation == "append":
                separator = (
                    "\n"
                    if current_content and not current_content.endswith("\n")
                    else ""
                )
                new_content = current_content + separator + content
            elif operation == "search_replace":
                if not search_pattern:
                    return (
                        "Error: search_pattern is required for search_replace operation"
                    )
                if search_pattern not in current_content:
                    return f"Error: Pattern '{search_pattern}' not found in block '{block}'"
                new_content = current_content.replace(search_pattern, content)
            else:
                return f"Error: Unknown operation '{operation}'. Use 'replace', 'append', or 'search_replace'"

            # Update the block (write to user-level for persistence, except 'context')
            success = await self.memory_manager.update_memory_block(
                label=block,
                content=new_content,
                chat_id=update_chat_id,  # None for persona/user/facts, chat_id for context
                user_id=user_id,
            )

            if success:
                logger.info(
                    f"Updated memory block '{block}' with operation '{operation}'"
                )
                return f"✓ Core memory block '{block}' updated successfully"
            else:
                return f"✗ Failed to update block '{block}'"

        except Exception as e:
            logger.error(f"Memory block update failed: {e}")
            return f"Error updating memory block: {str(e)}"

    def forward(
        self, block: str, operation: str, content: str, search_pattern: str = None
    ) -> str:
        """Synchronous wrapper for async forward - runs in main event loop."""
        import asyncio

        # If we have a reference to the main loop, use it (thread-safe)
        if self._main_loop and self._main_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.forward_async(block, operation, content, search_pattern),
                self._main_loop,
            )
            return future.result(timeout=30)  # 30 second timeout

        # Fallback: run in new loop (for testing/standalone use)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.forward_async(block, operation, content, search_pattern)
            )
        finally:
            loop.close()
            asyncio.set_event_loop(None)
