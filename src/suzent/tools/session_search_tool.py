"""Session search tool — recall and navigate past chat sessions.

A single tool with three modes (Hermes-style dispatch by which params are set):

* **Read** (``session_id`` set) — dump one session's messages, sanitized.
* **Discovery** (``query`` set) — full-text search across past sessions, returning
  match snippets with a context window and bookends.
* **Browse** (neither set) — list recent sessions chronologically.

All output is drawn from each message's clean AG-UI ``parts`` (see
``suzent.database.search``); reasoning traces are never surfaced, and tool output is
included only when ``role_filter`` requests it.
"""

from typing import Annotated, Optional

from pydantic import Field
from pydantic_ai import RunContext

from suzent.core.agent_deps import AgentDeps
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult

logger = get_logger(__name__)

VALID_ROLES = {"user", "assistant", "tool"}


def _parse_role_filter(role_filter: str) -> tuple[str, ...]:
    """Parse a comma-separated role filter into a validated tuple.

    Falls back to ``("user", "assistant")`` when nothing valid is given.
    """
    roles = tuple(
        r.strip().lower()
        for r in (role_filter or "").split(",")
        if r.strip().lower() in VALID_ROLES
    )
    return roles or ("user", "assistant")


def _format_messages(messages: list[dict]) -> str:
    lines = []
    for m in messages:
        text = (m.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{m.get('role', '?')}] {text}")
    return "\n".join(lines)


class SessionSearchTool(Tool):
    """Search and read past conversation sessions."""

    name = "SessionSearchTool"
    tool_name = "session_search"
    group = ToolGroup.MEMORY

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        query: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Full-text search across past sessions (Discovery mode). "
                "Supports the SQLite FTS5 query syntax. Omit to browse or read.",
            ),
        ] = None,
        session_id: Annotated[
            Optional[str],
            Field(
                default=None,
                description="Read one whole session by id (Read mode). Takes precedence "
                "over query.",
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(
                default=3,
                ge=1,
                le=10,
                description="Max sessions returned in Discovery/Browse modes.",
            ),
        ] = 3,
        role_filter: Annotated[
            str,
            Field(
                default="user,assistant",
                description="Comma-separated roles to include: 'user,assistant' "
                "(default), add 'tool' to include tool output, or 'tool' alone. "
                "Assistant reasoning is never shown.",
            ),
        ] = "user,assistant",
    ) -> ToolResult:
        """Recall past conversations: read a session, search them, or browse recent ones.

        Modes are chosen by which arguments are provided:
        - ``session_id`` → Read a whole session.
        - ``query`` → Discovery search across sessions.
        - neither → Browse recent sessions.
        """
        db = get_database()
        roles = _parse_role_filter(role_filter)
        current_chat_id = ctx.deps.chat_id

        try:
            if session_id:
                return self._read(db, session_id, roles)
            if query and query.strip():
                return self._discover(db, query, limit, roles, current_chat_id)
            return self._browse(db, limit, current_chat_id)
        except Exception as e:
            logger.error(f"session_search failed: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Session search failed: {e}",
            )

    # -- modes -------------------------------------------------------------

    def _read(self, db, session_id: str, roles: tuple[str, ...]) -> ToolResult:
        session = db.read_chat_session(session_id, role_filter=roles)
        if not session:
            return ToolResult.error_result(
                ToolErrorCode.FILE_NOT_FOUND,
                f"No session found with id '{session_id}'.",
            )
        header = f"Session '{session['title']}' ({session['total_messages']} messages"
        if session["truncated"]:
            header += ", showing first 20 + last 10"
        header += "):"
        body = _format_messages(session["messages"])
        return ToolResult.success_result(
            f"{header}\n\n{body}" if body else f"{header}\n\n(no visible messages)",
            metadata={
                "mode": "read",
                "session_id": session_id,
                "total_messages": session["total_messages"],
                "truncated": session["truncated"],
            },
        )

    def _discover(
        self,
        db,
        query: str,
        limit: int,
        roles: tuple[str, ...],
        current_chat_id: Optional[str],
    ) -> ToolResult:
        # Exclude the current session (recall is about *other* conversations) inside the
        # query, so excluding it never costs a result slot under the limit.
        results = db.search_chat_messages(
            query, limit=limit, role_filter=roles, exclude_chat_id=current_chat_id
        )
        if not results:
            return ToolResult.success_result(
                f"No past sessions matched '{query}'.",
                metadata={"mode": "discovery", "query": query, "match_count": 0},
            )

        blocks = [f"Found {len(results)} session(s) matching '{query}':\n"]
        for r in results:
            ctx_text = _format_messages(r["context"])
            blocks.append(
                f"### {r['title']}  (session_id: {r['chat_id']})\n"
                f"Last active: {r['updated_at']}\n"
                f"Match: {r['snippet']}\n\n"
                f"Context:\n{ctx_text}"
            )
        return ToolResult.success_result(
            "\n\n".join(blocks),
            metadata={
                "mode": "discovery",
                "query": query,
                "match_count": len(results),
            },
        )

    def _browse(self, db, limit: int, current_chat_id: Optional[str]) -> ToolResult:
        from suzent.database.search import sanitize_messages

        # Over-fetch by one so excluding the current chat still yields `limit` rows.
        summaries = db.list_chats(limit=limit + 1)
        summaries = [s for s in summaries if s.id != current_chat_id][:limit]
        if not summaries:
            return ToolResult.success_result(
                "No past sessions found.",
                metadata={"mode": "browse", "count": 0},
            )
        lines = ["Recent sessions:\n"]
        for s in summaries:
            # The sidebar summary count (s.messageCount) counts only assistant turns
            # and can be stale; recompute the visible (user+assistant) message count
            # live so Browse never reports a misleading "0 messages".
            chat = db.get_chat(s.id)
            msg_count = len(sanitize_messages(chat.messages or [])) if chat else 0
            preview = (s.lastMessage or "").strip()
            lines.append(
                f"- {s.title}  (session_id: {s.id})\n"
                f"  Updated: {s.updatedAt}  ·  {msg_count} messages\n"
                f"  {preview}"
            )
        return ToolResult.success_result(
            "\n".join(lines),
            metadata={"mode": "browse", "count": len(summaries)},
        )
