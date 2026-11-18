"""Full-text chat search infrastructure (SQLite FTS5).

Chats persist their messages in a per-chat JSONL log rather than
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

import hashlib
from typing import Any, Dict, List, Optional

from suzent.logger import get_logger

logger = get_logger(__name__)

FTS_TABLE = "chat_messages_fts"
# FTS5 cannot index an UNINDEXED column, so finding a chat's rows by
# ``chat_id`` reads every row's text. This plain table mirrors each FTS row
# (same rowid) with an index on ``chat_id`` and a digest of its text.
FTS_ROWS_TABLE = "chat_messages_fts_rows"

# Trigram needs at least this many chars to produce a token.
MIN_TRIGRAM_CHARS = 3

# Roles a session_search caller may ask to see. Reasoning is never surfaced.
DEFAULT_ROLE_FILTER = ("user", "assistant")
DEFAULT_TRANSCRIPT_CHAR_LIMIT = 20_000


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


def _text_digest(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def _ensure_fts_rows_table(conn: Any) -> None:
    """Create the rowid mirror, filling it from an index that predates it.

    It is built under a scratch name and renamed when complete, so an
    interrupted fill is redone on the next start instead of left partial.
    """
    exists = conn.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (FTS_ROWS_TABLE,),
    ).first()
    if exists:
        return
    scratch = f"{FTS_ROWS_TABLE}_build"
    conn.exec_driver_sql(f"DROP TABLE IF EXISTS {scratch}")
    conn.exec_driver_sql(
        f"CREATE TABLE {scratch} ("
        "id INTEGER PRIMARY KEY, chat_id TEXT NOT NULL, "
        "message_index INTEGER NOT NULL, role TEXT NOT NULL, digest TEXT NOT NULL)"
    )
    rows = [
        (rowid, chat_id, index, role, _text_digest(text or ""))
        for rowid, chat_id, index, role, text in conn.exec_driver_sql(
            f"SELECT rowid, chat_id, message_index, role, text FROM {FTS_TABLE}"
        )
    ]
    if rows:
        conn.exec_driver_sql(
            f"INSERT INTO {scratch} (id, chat_id, message_index, role, digest) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        logger.info("Indexed {} chat search row(s) by chat", len(rows))
    conn.exec_driver_sql(f"ALTER TABLE {scratch} RENAME TO {FTS_ROWS_TABLE}")
    conn.exec_driver_sql(
        f"CREATE INDEX IF NOT EXISTS ix_{FTS_ROWS_TABLE}_chat_id "
        f"ON {FTS_ROWS_TABLE} (chat_id)"
    )


def delete_chat_fts_rows(conn: Any, chat_id: str) -> None:
    """Delete a chat's search rows by rowid, inside the caller's transaction."""
    rowids = [
        (rowid,)
        for (rowid,) in conn.exec_driver_sql(
            f"SELECT id FROM {FTS_ROWS_TABLE} WHERE chat_id = ?", (chat_id,)
        )
    ]
    if not rowids:
        return
    conn.exec_driver_sql(f"DELETE FROM {FTS_TABLE} WHERE rowid = ?", rowids)
    conn.exec_driver_sql(f"DELETE FROM {FTS_ROWS_TABLE} WHERE chat_id = ?", (chat_id,))


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

    # User and tool rows carry plain text in `content`. Assistant rows do NOT — their
    # readable text lives in `parts`; the legacy `content` string is HTML-rendered
    # markdown (reasoning `<details>`, a2ui `<div>`). An assistant row without `parts`
    # has no safe text to surface, so return empty rather than leaking that markup.
    if role == "assistant":
        return ""
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


def bound_message_records(
    messages: List[Dict[str, Any]],
    max_chars: int = DEFAULT_TRANSCRIPT_CHAR_LIMIT,
) -> tuple[List[Dict[str, Any]], int, bool]:
    """Keep the newest visible messages within one shared transcript budget."""
    selected: List[Dict[str, Any]] = []
    selected_chars = 0
    message_truncated = False
    for message in reversed(messages):
        text_value = str(message.get("text") or "")
        line_size = len(str(message.get("role") or "")) + len(text_value) + 3
        separator_chars = 1 if selected else 0
        if selected and selected_chars + separator_chars + line_size > max_chars:
            break
        record = dict(message)
        if not selected and line_size > max_chars:
            available = max(1, max_chars - len(str(record.get("role") or "")) - 3)
            record["text"] = "[... message truncated ...]\n" + text_value[-available:]
            line_size = max_chars
            message_truncated = True
        selected.append(record)
        selected_chars += separator_chars + line_size

    selected.reverse()
    return selected, len(messages) - len(selected), message_truncated


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
            _ensure_fts_rows_table(conn)
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
                conn.exec_driver_sql(f"SELECT 1 FROM {FTS_ROWS_TABLE} LIMIT 1")
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
        """Bring *chat_id*'s FTS rows in line with freshly extracted message text.

        Indexes user + assistant text and tool output (so ``role_filter='tool'``
        searches work). Must run inside the same transaction as the chat write.
        Only rows whose text changed are deleted and inserted: trigram-indexing
        a long chat whole on every appended message held SQLite's write lock
        for up to a second.
        """
        # Take the write lock before reading the chat's rows, so a concurrent
        # write to the same chat can't slip in between and leave duplicates.
        conn.exec_driver_sql(f"DELETE FROM {FTS_ROWS_TABLE} WHERE id = -1")
        indexed: Dict[int, tuple[int, str, str]] = {}
        stale: List[int] = []
        for rowid, index, role, digest in conn.exec_driver_sql(
            f"SELECT id, message_index, role, digest FROM {FTS_ROWS_TABLE} "
            "WHERE chat_id = ?",
            (chat_id,),
        ):
            if index in indexed:
                stale.append(rowid)
            else:
                indexed[index] = (rowid, role, digest)
        wanted = {
            r["index"]: (r["role"], r["text"], _text_digest(r["text"]))
            for r in sanitize_messages(
                messages, role_filter=("user", "assistant", "tool")
            )
        }
        inserts = []
        for index, (rowid, role, digest) in indexed.items():
            want = wanted.get(index)
            if want is None or (want[0], want[2]) != (role, digest):
                stale.append(rowid)
        for index, (role, text, digest) in wanted.items():
            current = indexed.get(index)
            if current is None or current[1:] != (role, digest):
                inserts.append((index, role, text, digest))
        if stale:
            params = [(r,) for r in stale]
            conn.exec_driver_sql(f"DELETE FROM {FTS_TABLE} WHERE rowid = ?", params)
            conn.exec_driver_sql(f"DELETE FROM {FTS_ROWS_TABLE} WHERE id = ?", params)
        for index, role, text, digest in inserts:
            rowid = conn.exec_driver_sql(
                f"INSERT INTO {FTS_ROWS_TABLE} (chat_id, message_index, role, digest) "
                "VALUES (?, ?, ?, ?)",
                (chat_id, index, role, digest),
            ).lastrowid
            conn.exec_driver_sql(
                f"INSERT INTO {FTS_TABLE} (rowid, chat_id, message_index, role, text) "
                "VALUES (?, ?, ?, ?, ?)",
                (rowid, chat_id, index, role, text),
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
                delete_chat_fts_rows(conn, chat_id)
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

    def _like_match_chat_ids(self, query: str) -> List[str]:
        """Substring (LIKE) fallback for Discovery, newest chats first.

        Mirrors the chat-list search's message matching (``messages_search_filter``)
        so Discovery still works when FTS can't serve the query. Returns [] on error.
        """
        from sqlmodel import select
        from suzent.database.models import ChatModel, messages_search_filter

        if not self.fts_available():
            return []
        try:
            with self._session() as session:
                statement = (
                    select(ChatModel.id)
                    .where(messages_search_filter(query))
                    .order_by(ChatModel.updated_at.desc())
                )
                return [row for row in session.exec(statement).all()]
        except Exception as exc:
            logger.info("LIKE discovery fallback failed for {!r}: {}", query, exc)
            return []

    def search_chat_messages(
        self,
        query: str,
        limit: int = 3,
        context: int = 5,
        bookend: int = 3,
        role_filter: tuple[str, ...] = DEFAULT_ROLE_FILTER,
        exclude_chat_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Discovery mode: top-*limit* chats matching *query*.

        Each result: ``{chat_id, title, updated_at, snippet, context, bookends}``
        where ``context`` is the ±*context* sanitized messages around the first hit
        and ``bookends`` is the first/last *bookend* sanitized messages of the chat.

        Candidates come from FTS when it can serve the query, otherwise from a LIKE
        scan (short/CJK queries, invalid FTS syntax, or builds without FTS5) so
        Discovery degrades the same way the chat-list search does. ``exclude_chat_id``
        is dropped from candidates *before* the limit is applied, so excluding the
        current session never costs a result slot.
        """
        chat_ids = self.fts_match_chat_ids(query)
        if chat_ids is None:
            chat_ids = self._like_match_chat_ids(query)
        if not chat_ids:
            return []

        results: List[Dict[str, Any]] = []
        for chat_id in chat_ids:
            if len(results) >= max(1, limit):
                break
            if chat_id == exclude_chat_id:
                continue
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
        offset: int | None = None,
        page_size: int = 20,
    ) -> Optional[Dict[str, Any]]:
        """Read sanitized messages as a summary or an explicit chronological page."""
        chat = self.get_chat(chat_id)
        if not chat:
            return None
        cleaned = sanitize_messages(chat.messages or [], role_filter=role_filter)
        total = len(cleaned)
        truncated = False
        page: dict[str, Any] = {}
        if offset is not None:
            if offset < 0 or not 1 <= page_size <= 100:
                raise ValueError(
                    "offset must be nonnegative and page_size must be 1–100"
                )
            cleaned = cleaned[offset : offset + page_size]
            next_offset = offset + len(cleaned)
            page = {
                "offset": offset,
                "next_offset": next_offset if next_offset < total else None,
            }
            truncated = offset > 0 or next_offset < total
        elif total > head + tail:
            cleaned = cleaned[:head] + cleaned[-tail:]
            truncated = True
        return {
            **page,
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
