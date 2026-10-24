"""
Memory tools exposed to agents.

MemorySearchTool reads memory. MemoryUpdateTool records what the user explicitly
asks to remember, retract or correct, so it reaches the same daily log and rejected
list capture uses. Curated files and vault pages are still edited with the ordinary
file tools.
"""

from typing import Annotated, Literal, Optional
from datetime import datetime

from pydantic import Field
from pydantic_ai import RunContext
from suzent.core.agent_deps import AgentDeps
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.logger import get_logger

logger = get_logger(__name__)


class MemorySearchTool(Tool):
    """
    Search long-term archival memory for relevant information.
    """

    name = "MemorySearchTool"
    tool_name = "memory_search"
    group = ToolGroup.MEMORY

    def __init__(self):
        super().__init__()

    @staticmethod
    async def _resolve_manager():
        """Return the live memory manager, lazily initializing it if a startup
        race left it unbuilt. Returns None only if memory is disabled or init
        genuinely failed."""
        from suzent.memory.lifecycle import get_memory_manager, init_memory_system

        mm = get_memory_manager()
        if mm is not None:
            return mm
        try:
            await init_memory_system()
        except Exception as e:
            logger.warning(f"Lazy memory init failed: {e}")
        return get_memory_manager()

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
            # The manager is built by a fire-and-forget background task at server
            # startup, so an early search can race ahead of it (and the deps for
            # this turn captured memory_manager=None). Fall back to the live global,
            # and lazily run init if it hasn't completed yet. init is idempotent.
            mm = await self._resolve_manager()
        if not mm:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                "Memory system is still initializing. Please try again in a moment.",
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

                # hybrid_search reports a combined "score"; semantic_search reports
                # "similarity". Check all so relevance isn't always shown as 0.00.
                similarity = (
                    mem.get("similarity")
                    or mem.get("semantic_score")
                    or mem.get("score")
                    or 0
                )

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


# The user's message is the evidence for an explicit memory; a pasted document should
# not be.
EVIDENCE_CHARS = 300


class MemoryUpdateTool(Tool):
    """
    Remember, retract or correct a memory when the user asks, or keep a lesson from an
    outcome or a pointer from a source the agent read.
    """

    name = "MemoryUpdateTool"
    tool_name = "memory_update"
    group = ToolGroup.MEMORY

    @staticmethod
    def _user_words(ctx: RunContext[AgentDeps]) -> str:
        from suzent.core.system_reminder import strip_system_reminders

        prompt = getattr(ctx, "prompt", None)
        if not isinstance(prompt, str):
            return ""
        return " ".join(strip_system_reminders(prompt).split())[:EVIDENCE_CHARS]

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        fact: Annotated[
            Optional[str],
            Field(
                description=(
                    "What to remember, one sentence, subject first "
                    "('User prefers ...'). Omit when only retracting."
                )
            ),
        ] = None,
        retract: Annotated[
            Optional[str],
            Field(
                description=(
                    "A memory to take back, as the user described it. With `fact` "
                    "this is a correction: the old claim out, the new one in."
                )
            ),
        ] = None,
        retract_as: Annotated[
            Literal["wrong", "outdated"],
            Field(
                description=(
                    "wrong: it was never true; it is kept from coming back. "
                    "outdated: it was true and no longer is."
                )
            ),
        ] = "wrong",
        kind: Annotated[
            Literal["user", "experience", "world"],
            Field(
                description=(
                    "user: about the user. experience: a lesson from an outcome. "
                    "world: how something works, with where it came from."
                )
            ),
        ] = "user",
        outcome: Annotated[
            Optional[str],
            Field(
                description=(
                    "For kind=experience: what happened, e.g. 'tests passed', "
                    "'the user accepted it', 'the user corrected it to ...'."
                )
            ),
        ] = None,
        source: Annotated[
            Optional[str],
            Field(description="For kind=world: the path or URL the fact comes from."),
        ] = None,
        category: Annotated[
            Literal["personal", "preference", "goal", "context", "technical"],
            Field(description="Category of the fact."),
        ] = "context",
        horizon: Annotated[
            Literal["durable", "dated"],
            Field(
                description=(
                    "durable: true until something changes it. dated: true now but "
                    "will expire."
                )
            ),
        ] = "durable",
    ) -> ToolResult:
        """Remember, retract or correct a memory.

        Use it in three cases:
        - The user says to remember something, or that something you know about them
          is wrong or has changed (kind=user).
        - An outcome taught you something: the user accepted or corrected your result,
          or an approach worked after another failed (kind=experience). Write the
          situation, what was tried and the lesson, and give `outcome`.
        - You learned from a file, doc or page where something lives or why it is so,
          and the source does not say it plainly (kind=world). Give `source`.
        Facts about the user are captured from the conversation on their own; do not
        call this to save what you noticed. Never save repo state: versions, PR
        numbers, branches, file lists.

        Args:
            fact: What to remember.
            retract: A memory to take back.
            retract_as: Whether the retracted memory was wrong or is outdated.
            kind: What kind of memory the fact is.
            category: Category of the fact.
            horizon: Whether the fact lasts or expires.
            outcome: What happened, for a lesson.
            source: Where a world fact comes from.
        """
        if not (fact and fact.strip()) and not (retract and retract.strip()):
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "Give a fact to remember, a memory to retract, or both.",
            )
        outcome = " ".join((outcome or "").split())
        source = " ".join((source or "").split())
        if fact and fact.strip():
            if kind == "experience" and not outcome:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "A lesson needs its outcome: say what happened in `outcome`.",
                )
            if kind == "world" and not source:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    "A world fact needs its source: give the path or URL in `source`.",
                )
        match kind:
            case "experience":
                evidence = f"outcome: {outcome}"[:EVIDENCE_CHARS]
            case "world":
                evidence = f"source: {source}"[:EVIDENCE_CHARS]
            case _:
                evidence = self._user_words(ctx)
        mm = ctx.deps.memory_manager or await MemorySearchTool._resolve_manager()
        if not mm:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                "Memory system is still initializing. Please try again in a moment.",
            )
        try:
            result = await mm.apply_memory_update(
                user_id=ctx.deps.user_id,
                chat_id=ctx.deps.chat_id,
                fact=fact,
                retract=retract,
                retract_as=retract_as,
                kind=kind,
                category=category,
                horizon=horizon,
                evidence=evidence,
            )
        except Exception as e:
            logger.error(f"Memory update failed: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Error updating memory: {e}"
            )

        lines: list[str] = []
        if retract:
            hidden = result["retracted"]
            lines.append(
                f"Retracted as {retract_as}; {len(hidden)} stored memory row(s) hidden."
            )
            lines += [f"- {c}" for c in hidden]
        if result["written"]:
            lines.append(f"Remembered: {result['written']}")
        return ToolResult.success_result(
            "\n".join(lines),
            metadata={
                "retracted": len(result["retracted"]),
                "written": bool(result["written"]),
            },
        )
