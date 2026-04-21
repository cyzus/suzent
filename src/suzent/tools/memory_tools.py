"""
Memory tools exposed to agents.

Only MemorySearchTool is exposed — agents write to memory files directly via
the standard file tools (edit_file / write_file) rather than a dedicated block
update tool.  This keeps the file system as the single source of truth.
"""

from typing import Annotated
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
