"""
Memory tools exposed to agents.
"""

from typing import Annotated, Optional, Literal
from datetime import datetime

from pydantic import Field
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolResult
from suzent.logger import get_logger

logger = get_logger(__name__)


class MemorySearchTool(Tool):
    """
    Search long-term archival memory for relevant information.
    """

    name = "MemorySearchTool"
    tool_name = "memory_search"

    def __init__(self):
        super().__init__()

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        query: Annotated[
            str,
            Field(
                description="Natural-language query describing what to look for in memory."
            ),
        ],
        limit: Annotated[
            int,
            Field(
                default=10,
                ge=1,
                le=20,
                description="Maximum number of memories to return.",
            ),
        ] = 10,
    ) -> ToolResult:
        """Search long-term archival memory for relevant information.

        Uses semantic similarity to find relevant memories even if the exact words differ.

        Args:
            query: What to search for in memory (use natural language).
            limit: Maximum number of results to return (default 10).
        """
        mm = ctx.deps.memory_manager
        if not mm:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                "Memory system not available.",
            )
        user_id = ctx.deps.user_id

        try:
            memories = await mm.search_memories(
                query=query,
                limit=limit,
                chat_id=None,  # Always search user-level memories
                user_id=user_id,
            )

            if not memories:
                return ToolResult.success_result(
                    "No relevant memories found.",
                    metadata={"query": query, "match_count": 0, "limit": limit},
                )

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
            return ToolResult.success_result(
                result,
                metadata={"query": query, "match_count": len(memories), "limit": limit},
            )

        except Exception as e:
            logger.error(f"Memory search failed: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Error searching memories: {str(e)}",
                metadata={"query": query, "limit": limit},
            )


class MemoryBlockUpdateTool(Tool):
    """
    Update core memory blocks that are always visible in context.
    """

    name = "MemoryBlockUpdateTool"
    tool_name = "memory_block_update"

    def __init__(self):
        super().__init__()

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        block: Annotated[
            Literal["persona", "user", "facts", "context"],
            Field(
                description="Core memory block to update. 'context' is session-scoped; others are long-term."
            ),
        ],
        operation: Annotated[
            Literal["replace", "append", "search_replace"],
            Field(
                description="How to update the block. search_replace requires search_pattern to exist in the current content."
            ),
        ],
        content: Annotated[
            str,
            Field(
                description="Replacement or appended content for the selected memory block."
            ),
        ],
        search_pattern: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Required when operation='search_replace'; exact substring to replace.",
            ),
        ] = None,
    ) -> ToolResult:
        """Update core memory blocks that are always visible in your context.

        Core memory blocks:
        - persona: Your identity, role, capabilities, and preferences
        - user: Information about the current user (name, preferences, context)
        - facts: Key facts you should always remember
        - context: Current session context (active tasks, goals, constraints)

        Args:
            block: Which block to update ('persona', 'user', 'facts', or 'context').
            operation: Operation to perform ('replace', 'append', or 'search_replace').
            content: New content or content to append.
            search_pattern: For search_replace: the text pattern to find and replace.
        """
        mm = ctx.deps.memory_manager
        if not mm:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                "Memory system not available.",
            )
        user_id = ctx.deps.user_id
        chat_id = ctx.deps.chat_id

        try:
            valid_blocks = ["persona", "user", "facts", "context"]
            if block not in valid_blocks:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"Invalid block '{block}'. Must be one of: {', '.join(valid_blocks)}",
                )

            valid_operations = ["replace", "append", "search_replace"]
            if operation not in valid_operations:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"Unknown operation '{operation}'. Use 'replace', 'append', or 'search_replace'",
                )

            # Decide scope: 'context' is chat-specific, others are user-level
            # This ensures persona/user/facts persist across all conversations
            update_chat_id = chat_id if block == "context" else None

            # Get current content (read from chat-specific or user-level)
            current_blocks = await mm.get_core_memory(
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
                    return ToolResult.error_result(
                        ToolErrorCode.MISSING_REQUIRED_PARAM,
                        "search_pattern is required for search_replace operation",
                    )
                if search_pattern not in current_content:
                    return ToolResult.error_result(
                        ToolErrorCode.NO_MATCH,
                        f"Pattern '{search_pattern}' not found in block '{block}'",
                        metadata={"block": block, "operation": operation},
                    )
                new_content = current_content.replace(search_pattern, content)

            # Update the block (write to user-level for persistence, except 'context')
            success = await mm.update_memory_block(
                label=block,
                content=new_content,
                chat_id=update_chat_id,  # None for persona/user/facts, chat_id for context
                user_id=user_id,
            )

            if success:
                logger.info(
                    f"Updated memory block '{block}' with operation '{operation}'"
                )
                return ToolResult.success_result(
                    f"Core memory block '{block}' updated successfully",
                    metadata={"block": block, "operation": operation},
                )
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Failed to update block '{block}'",
                metadata={"block": block, "operation": operation},
            )

        except Exception as e:
            logger.error(f"Memory block update failed: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Error updating memory block: {str(e)}",
                metadata={"block": block, "operation": operation},
            )
