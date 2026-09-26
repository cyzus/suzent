"""The project guard the goal and task tools share.

Every tool in this package is scoped to one project, and each used to inline
both the lookup and the refusal. Kept in a leaf module rather than the package
``__init__`` so importing it does not pull the whole task suite in behind it.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from suzent.core.project_context import resolve_project_id
from suzent.tools.base import ToolErrorCode, ToolResult

NO_PROJECT_MESSAGE = "Current chat is not linked to a project."


def require_project_id(ctx: Any) -> Tuple[Optional[str], Optional[ToolResult]]:
    """Return ``(project_id, None)``, or ``(None, error)`` when the chat has none.

    Callers that can still do useful work without a project -- ``update_task``
    resolves one only to check the task against it -- should call
    :func:`suzent.core.project_context.resolve_project_id` directly instead.
    """
    project_id = resolve_project_id(getattr(ctx.deps, "chat_id", None))
    if not project_id:
        return None, ToolResult.error_result(
            ToolErrorCode.INVALID_ARGUMENT, NO_PROJECT_MESSAGE
        )
    return project_id, None
