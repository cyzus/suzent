"""Full-text chat search infrastructure (SQLite FTS5).

Chats persist their messages as a JSON array on ``ChatModel.messages`` rather than
one row per message, so FTS5's external-content sync triggers cannot be used. Instead
we maintain a plain FTS5 table (``chat_messages_fts``) and reindex a chat's rows from
the application layer whenever its messages change (see ChatOperationsMixin write paths).

Indexed/returned text comes from the **AG-UI structured ``parts``** of each message —
never the legacy HTML ``content`` string — so reasoning ``<details>`` and a2ui ``<div>``
markup never enter the index or the agent-facing output. See
``project_session_search_plan.md`` for the full design.

Tokenizer: ``trigram``. It indexes 3-char windows, which gives substring matching for
both ASCII and CJK text (``unicode61`` treats an undelimited CJK run as one token and
cannot match a substring of it). The cost is that queries shorter than 3 chars can't be
served by the index; for those we signal the caller to fall back to a ``LIKE`` scan so
the existing chat-list search behaviour (2-char CJK substrings included) never regresses.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

FTS_TABLE = "chat_messages_fts"

# Trigram needs at least this many chars to produce a token.
MIN_TRIGRAM_CHARS = 3

# Roles a session_search caller may ask to see. Reasoning is never surfaced.
DEFAULT_ROLE_FILTER = ("user", "assistant")


def _supports_fts5(conn: Any) -> bool:
    """Return True if the live SQLite build can create an FTS5 table."""
    try:
        conn.exec_driver_sql(
            "CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_probe USING fts5(x)"
        )
        conn.exec_driver_sql("DROP TABLE IF EXISTS _fts5_probe")
        return True
    except Exception as exc:  # pragma: no cover - depends on sqlite build
        logger.warning(
            "SQLite FTS5 not available; chat search falls back to LIKE: {}", exc
        )
        return False


def _message_searchable_text(message: Dict[str, Any], include_tool: bool) -> str:
    """Extract the indexable / agent-visible text from one display message.

    Reads AG-UI ``parts`` for assistant messages (text + optionally tool output),
    and the plain ``content`` for user/tool rows. Reasoning and a2ui parts are
    never included.
    """
    role = message.get("role")
    parts = message.get("parts")

    if isinstance(parts, list) and parts:
        chunks: List[str] = []
        for part in parts:
            if not isinstance(part, dict):
                continue
            ptype = part.get("type")
            if ptype == "text":
                chunks.append(str(part.get("text", "")))
            elif ptype == "tool" and include_tool:
                name = part.get("toolName", "")
                output = part.get("output", "")
                chunks.append(f"[tool:{name}] {output}".strip())
            # reasoning / a2ui: intentionally skipped
        return "\n".join(c for c in chunks if c).strip()

    # User rows and tool rows carry plain text directly.
    if role == "tool":
        return str(message.get("content", "")) if include_tool else ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def sanitize_messages(
    messages: List[Dict[str, Any]],
    role_filter: tuple[str, ...] = DEFAULT_ROLE_FILTER,
) -> List[Dict[str, Any]]:
    """Project stored display messages into clean, role-filtered records.

    Returns a list of ``{index, role, text, timestamp}`` dicts containing only the
    roles in *role_filter*. Reasoning is always dropped; tool output is included only
    when ``"tool"`` is in *role_filter*.
    """
    include_tool = "tool" in role_filter
    out: List[Dict[str, Any]] = []
    for idx, msg in enumerate(messages or []):
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "")
        # "system_triggered" rows (cron/heartbeat) ride along with assistant view.
        visible_role = "assistant" if role == "system_triggered" else role
        if visible_role not in role_filter:
            continue
        cleaned = _message_searchable_text(msg, include_tool=include_tool)
        if not cleaned:
            continue
        out.append(
            {
                "index": idx,
                "role": role,
                "text": cleaned,
                "timestamp": msg.get("timestamp"),
            }
        )
    return out


class ChatSearchMixin:
    """FTS5-backed full-text search over chat messages.

    Mixed into ``ChatDatabase``. Owns the FTS table lifecycle, per-chat reindexing,
    and the query methods used by both ``session_search`` and the chat-list search.
    """

    # -- table lifecycle ---------------------------------------------------

    def _ensure_fts_table(self) -> bool:
        """Create the FTS5 table if missing. Returns False when FTS5 is unavailable."""
        with self.engine.connect() as conn:
            if not _supports_fts5(conn):
                return False
            conn.exec_driver_sql(
                f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS {FTS_TABLE} USING fts5(
                    chat_id UNINDEXED,
                    message_index UNINDEXED,
                    role UNINDEXED,
                    text,
                    tokenize = 'trigram'
                )
                """
            )
            conn.commit()
        self._fts_available_cache = True
        return True

    def fts_available(self) -> bool:
        """Whether the FTS table exists and is usable (memoized after first check)."""
        cached = getattr(self, "_fts_available_cache", None)
        if cached is not None:
            return cached
        try:
            with self.engine.connect() as conn:
                conn.exec_driver_sql(f"SELECT 1 FROM {FTS_TABLE} LIMIT 1")
            available = True
        except Exception:
            available = False
        self._fts_available_cache = available
        return available

    # -- indexing ----------------------------------------------------------

    @staticmethod
    def _reindex_chat_fts(
        conn: Any, chat_id: str, messages: List[Dict[str, Any]]
    ) -> None:
        """Replace all FTS rows for *chat_id* with freshly extracted message text.

        Indexes user + assistant text and tool output (so ``role_filter='tool'``
        searches work). Must run inside the same transaction as the chat write.
        """
        conn.exec_driver_sql(f"DELETE FROM {FTS_TABLE} WHERE chat_id = ?", (chat_id,))
        rows = sanitize_messages(messages, role_filter=("user", "assistant", "tool"))
        if not rows:
            return
        conn.exec_driver_sql(
            f"INSERT INTO {FTS_TABLE} (chat_id, message_index, role, text) VALUES "
            + ",".join(["(?, ?, ?, ?)"] * len(rows)),
            tuple(v for r in rows for v in (chat_id, r["index"], r["role"], r["text"])),
        )

    def reindex_chat(self, chat_id: str, messages: List[Dict[str, Any]]) -> None:
        """Public, self-contained reindex (own transaction). Used by backfill."""
        if not self.fts_available():
            return
        try:
            with self.engine.connect() as conn:
                self._reindex_chat_fts(conn, chat_id, messages)
                conn.commit()
        except Exception as exc:
            logger.warning("FTS reindex failed for chat {}: {}", chat_id, exc)

    def remove_chat_from_fts(self, chat_id: str) -> None:
        """Drop a deleted chat's rows from the index."""
        if not self.fts_available():
            return
        try:
            with self.engine.connect() as conn:
                conn.exec_driver_sql(
                    f"DELETE FROM {FTS_TABLE} WHERE chat_id = ?", (chat_id,)
                )
                conn.commit()
        except Exception as exc:
            logger.warning("FTS delete failed for chat {}: {}", chat_id, exc)

    # -- querying ----------------------------------------------------------

    def fts_match_chat_ids(self, query: str) -> Optional[List[str]]:
        """Return chat_ids whose messages match *query*, best-rank first.

        Returns None when FTS can't serve the query (unavailable, or shorter than the
        trigram minimum) so the caller falls back to a LIKE scan.
        """
        if not self.fts_available():
            return None
        if len(query.strip()) < MIN_TRIGRAM_CHARS:
            return None
        try:
            with self.engine.connect() as conn:
                result = conn.exec_driver_sql(
                    f"SELECT chat_id FROM {FTS_TABLE} WHERE {FTS_TABLE} MATCH ? "
                    f"ORDER BY rank",
                    (query,),
                )
                seen: List[str] = []
                seen_set = set()
                for (cid,) in result:
                    if cid not in seen_set:
                        seen_set.add(cid)
                        seen.append(cid)
                return seen
        except Exception as exc:
            # An invalid FTS query string (bad syntax) should degrade, not crash.
            logger.info("FTS query failed for {!r}: {}", query, exc)
            return None

    def search_chat_messages(
        self,
        query: str,
        limit: int = 3,
        context: int = 5,
        bookend: int = 3,
        role_filter: tuple[str, ...] = DEFAULT_ROLE_FILTER,
    ) -> List[Dict[str, Any]]:
        """Discovery mode: top-*limit* chats matching *query*.

        Each result: ``{chat_id, title, updated_at, snippet, context, bookends}``
        where ``context`` is the ±*context* sanitized messages around the first hit
        and ``bookends`` is the first/last *bookend* sanitized messages of the chat.
        """
        chat_ids = self.fts_match_chat_ids(query)
        if not chat_ids:
            return []

        results: List[Dict[str, Any]] = []
        for chat_id in chat_ids[: max(1, limit)]:
            chat = self.get_chat(chat_id)
            if not chat:
                continue
            if self._is_hidden_platform(chat):
                continue
            cleaned = sanitize_messages(chat.messages or [], role_filter=role_filter)
            if not cleaned:
                continue

            hit_pos = self._first_hit_position(cleaned, query)
            lo = max(0, hit_pos - context)
            hi = min(len(cleaned), hit_pos + context + 1)
            window = cleaned[lo:hi]

            bookends = {
                "first": cleaned[:bookend],
                "last": cleaned[-bookend:] if len(cleaned) > bookend else [],
            }
            results.append(
                {
                    "chat_id": chat_id,
                    "title": chat.title,
                    "updated_at": chat.updated_at.isoformat()
                    if chat.updated_at
                    else None,
                    "snippet": cleaned[hit_pos]["text"][:300],
                    "context": window,
                    "bookends": bookends,
                }
            )
        return results

    def read_chat_session(
        self,
        chat_id: str,
        role_filter: tuple[str, ...] = DEFAULT_ROLE_FILTER,
        head: int = 20,
        tail: int = 10,
    ) -> Optional[Dict[str, Any]]:
        """Read mode: a whole session, sanitized. Large sessions show head+tail."""
        chat = self.get_chat(chat_id)
        if not chat:
            return None
        cleaned = sanitize_messages(chat.messages or [], role_filter=role_filter)
        total = len(cleaned)
        truncated = False
        if total > head + tail:
            cleaned = cleaned[:head] + cleaned[-tail:]
            truncated = True
        return {
            "chat_id": chat_id,
            "title": chat.title,
            "updated_at": chat.updated_at.isoformat() if chat.updated_at else None,
            "total_messages": total,
            "truncated": truncated,
            "messages": cleaned,
        }

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _first_hit_position(cleaned: List[Dict[str, Any]], query: str) -> int:
        """Best-effort index of the message most likely to contain the match.

        FTS rank points at a chat, not a message; we re-locate the term within the
        sanitized list for the context window. Falls back to 0.
        """
        terms = [t.strip('"').lower() for t in query.split() if t.strip('"')]
        for i, msg in enumerate(cleaned):
            low = msg["text"].lower()
            if any(t in low for t in terms):
                return i
        return 0

    @staticmethod
    def _is_hidden_platform(chat: Any) -> bool:
        from suzent.database.chats import HIDDEN_CHAT_PLATFORMS

        config = getattr(chat, "config", None) or {}
        return config.get("platform") in HIDDEN_CHAT_PLATFORMS
