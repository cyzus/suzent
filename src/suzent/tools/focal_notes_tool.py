"""SUZENT's own notes: the context.md of its hidden system project.

The notes load into SUZENT's core memory as the Context block on every turn.
They hold what stays true about how the user wants SUZENT to work, never
project or task status, which SUZENT reads fresh each turn.
"""

from typing import Annotated

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolResult

logger = get_logger(__name__)

# Past this the core-memory section truncates the Context block.
MAX_NOTES_CHARS = 8000


class FocalNotesTool(Tool):
    """Edit your notes, the Context block of your core memory.

    Only SUZENT is equipped with it, and it refuses any other chat.
    """

    name = "FocalNotesTool"
    tool_name = "update_notes"
    display_name = "Keep notes"
    # Not user-configurable and not discoverable through ToolSearch: Focal only.
    group = ""
    deferrable = False
    session_guidance = (
        "Your notes (the Context block) are where you keep what stays true about "
        "how the user wants you to work: what to bring to them and what to handle, "
        "what counts as urgent, when not to disturb them, which project they mean "
        "by a nickname, how they like reports. Update them with update_notes when "
        "the user tells you such a rule, or you notice one they keep repeating. "
        "Never record project or task status there: it goes stale, and you read "
        "it fresh every turn."
    )

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        new_text: Annotated[
            str,
            Field(
                description=(
                    "Text to add, or to put in place of old_text. Empty with "
                    "old_text deletes it."
                )
            ),
        ],
        old_text: Annotated[
            str,
            Field(
                description=(
                    "Exact text in your notes to replace. Leave empty to append "
                    "new_text at the end."
                )
            ),
        ] = "",
    ) -> ToolResult:
        from suzent.core.focal_agent import FOCAL_CHAT_ID, is_focal_chat_id

        if not is_focal_chat_id(ctx.deps.chat_id):
            return ToolResult.error_result(
                ToolErrorCode.PERMISSION_DENIED,
                "update_notes belongs to SUZENT; project notes live in context.md.",
            )
        if not old_text and not new_text.strip():
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "Give new_text, old_text, or both."
            )

        path = get_database().get_project_dir(FOCAL_CHAT_ID) / "context.md"
        notes = path.read_text(encoding="utf-8") if path.exists() else ""
        if old_text:
            matches = notes.count(old_text)
            if matches != 1:
                return ToolResult.error_result(
                    ToolErrorCode.INVALID_ARGUMENT,
                    f"old_text must match your notes exactly once; it matched {matches} times.",
                )
            updated = notes.replace(old_text, new_text)
        else:
            updated = f"{notes.rstrip()}\n{new_text.strip()}\n".lstrip()

        if len(updated) > MAX_NOTES_CHARS:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                f"Notes are limited to {MAX_NOTES_CHARS:,} characters; condense "
                "or remove entries first.",
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        logger.info("SUZENT updated its notes ({} chars)", len(updated))
        return ToolResult.success_result(f"Notes updated. They now read:\n\n{updated}")
