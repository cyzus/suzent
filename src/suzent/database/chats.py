import copy
import json
import uuid
from contextlib import ExitStack
from datetime import datetime, timezone
import re
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, or_, text, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select as sa_select
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, col, delete, select

from suzent.logger import get_logger

from .chat_log import (
    ChatEventLog,
    ChatLogError,
    PendingAppend,
    Projection,
    RetryCheckpoint,
    normalize_json,
    project_chat,
    project_state,
    projection_differences,
    state_bytes,
    visible_messages,
)
from .models import (
    ChatLogIndexModel,
    ChatModel,
    ChatStatusModel,
    ChatSummaryModel,
    InputSuggestionModel,
    ProjectModel,
    _postprocess_metrics,
    messages_search_filter,
)

SUMMARY_LAST_MESSAGE_KEY = "_summary_last_message"
SUMMARY_VISIBLE_COUNT_KEY = "_summary_visible_assistant_count"
CHAT_SCOPED_CONFIG_KEYS = frozenset(
    {
        "tool_approval_policy",
        "permission_policies",
        "permission_mode",
        "platform",
        "runtime",
        "acp_agent_id",
        "acp_session_id",
        "acp_cwd",
        "sender_id",
        "target_id",
        "cron_job_id",
        "parent_chat_id",
        "forked_from_chat_id",
        "forked_from_chat_title",
        "forked_from_message_index",
        "unread_count",
    }
)

# Sentinel for rewrite_chat_messages(agent_state=...) so "omit" (leave stored state)
# is distinguishable from an explicit None (restore a NULL checkpoint state).
_UNSET = object()

# Platforms hidden from the user's chat list: the autonomous dream consolidation chat,
# and the Focal Agent, which has its own top-level sidebar slot instead of a row in a
# project. Sub-agent chats are intentionally kept visible (nested under their parent
# agent in the UI), so they are NOT excluded here.
HIDDEN_CHAT_PLATFORMS = ("dream", "focal")

logger = get_logger(__name__)


def _json_column(raw: Any, default: Any) -> Any:
    """Decode a JSON column read with raw SQL, where it arrives as text."""
    if raw is None:
        return default
    return json.loads(raw) if isinstance(raw, (str, bytes)) else raw


def _reusable_chat_config(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Copy model/tool settings without inheriting source-session state."""
    return {
        key: value
        for key, value in (config or {}).items()
        if key not in CHAT_SCOPED_CONFIG_KEYS and not key.startswith("heartbeat_")
    }


def _apply_chat_filters(statement, search, platform, project_id, fts_ids=None):
    """Apply common search/platform/project filters to a ChatModel statement.

    The hidden dream consolidation chat is always excluded from listing — it is an
    internal background agent, not a user conversation (it surfacing in the sidebar
    is the bug this fixes). Sub-agent chats remain visible by design.

    When *fts_ids* is a list, message-content matching is served by the FTS index
    (``ChatModel.id IN fts_ids``) instead of the ``LIKE`` scan over the JSON column;
    title matching still uses ``LIKE``. ``fts_ids=None`` means FTS was unavailable or
    could not serve the query, so we fall back to the original ``LIKE`` message scan.
    """
    # SQLite json_extract returns the platform string or NULL; exclude the hidden set.
    placeholders = ", ".join(f"'{p}'" for p in HIDDEN_CHAT_PLATFORMS)
    statement = statement.where(
        text(
            "(json_extract(config, '$.platform') IS NULL "
            f"OR json_extract(config, '$.platform') NOT IN ({placeholders}))"
        )
    )
    if search:
        if fts_ids is None:
            message_match = messages_search_filter(search)
        elif fts_ids:
            message_match = ChatModel.id.in_(fts_ids)
        else:
            # FTS ran and matched nothing — no message hits possible.
            message_match = None
        title_match = ChatModel.title.contains(search)
        statement = statement.where(
            or_(title_match, message_match)
            if message_match is not None
            else title_match
        )
    if project_id is not None:
        statement = statement.where(ChatModel.project_id == project_id)
    if platform == "social":
        statement = statement.where(
            text("json_extract(config, '$.platform') IS NOT NULL")
        )
    elif platform == "personal":
        statement = statement.where(text("json_extract(config, '$.platform') IS NULL"))
    return statement


def _message_content_text(content: Any) -> str:
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)
        return " ".join(text_parts)
    if isinstance(content, str):
        return content
    return str(content) if content is not None else ""


def _clean_message_preview(content: Any) -> str:
    text_content = _message_content_text(content)
    clean_content = re.sub(
        r"<details\b[^>]*>.*?</details>", "", text_content, flags=re.DOTALL
    )
    return re.sub(r"<[^>]+>", "", clean_content).strip()


def _summarize_messages(
    messages: Optional[List[Dict[str, Any]]],
) -> tuple[int, Optional[str]]:
    """Return sidebar summary data without leaking tool detail blocks."""
    safe_messages = messages or []
    last_message = None
    if safe_messages:
        last_msg = safe_messages[-1]
        content = last_msg.get("content") if isinstance(last_msg, dict) else last_msg
        clean_content = _clean_message_preview(content)
        last_message = clean_content[:100] if clean_content else None
        if last_message and len(clean_content) > 100:
            last_message += "..."

    visible_count = sum(
        1
        for message in safe_messages
        if isinstance(message, dict)
        and message.get("role") == "assistant"
        and isinstance(message.get("content"), str)
        and message["content"].strip()
    )
    return visible_count, last_message


def _is_draft_of_run(row: Any, run_id: Optional[str]) -> bool:
    """True when *row* is the live streaming draft written by *run_id*."""
    if not run_id or not isinstance(row, dict):
        return False
    return (
        row.get("role") == "assistant"
        and bool(row.get("_streaming_draft"))
        and row.get("_streaming_run_id") == run_id
    )


def _with_message_summary(
    config: Optional[Dict[str, Any]],
    messages: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    next_config = dict(config or {})
    visible_count, last_message = _summarize_messages(messages)
    next_config[SUMMARY_VISIBLE_COUNT_KEY] = visible_count
    next_config[SUMMARY_LAST_MESSAGE_KEY] = last_message
    return next_config


def _message_summary(messages: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    visible_count, last_message = _summarize_messages(messages)
    return {
        SUMMARY_VISIBLE_COUNT_KEY: visible_count,
        SUMMARY_LAST_MESSAGE_KEY: last_message,
    }


def _config_path(key: str) -> str:
    return '$."' + key.replace('"', '\\"') + '"'


# Coerces a missing or non-object config to {} so json_set has an object to edit.
_STORED_CONFIG_SQL = "CASE WHEN json_type(config) = 'object' THEN config ELSE '{}' END"


def _set_config_keys(session: Any, chat_id: str, updates: Dict[str, Any]) -> None:
    """Write *updates* into the stored config without touching any other key.

    Copying the config out, editing it and writing the whole dict back loses
    every key another writer committed in between: a streaming draft that read
    the config just before a pending approval was saved would wipe that
    approval, and the user's decision on it would then be rejected as stale.
    ``json_set`` edits the row the UPDATE holds locked, so it cannot do that.
    """
    if not updates:
        return
    params: Dict[str, Any] = {"chat_id": chat_id}
    assignments = []
    for index, (key, value) in enumerate(updates.items()):
        params[f"path_{index}"] = _config_path(key)
        params[f"value_{index}"] = json.dumps(value, default=str)
        assignments.append(f":path_{index}, json(:value_{index})")
    session.execute(
        text(
            f"UPDATE chats SET config = json_set({_STORED_CONFIG_SQL}, "
            f"{', '.join(assignments)}) WHERE id = :chat_id"
        ),
        params,
    )


def _replace_config(
    session: Any, chat_id: str, config: Dict[str, Any], keep: List[str]
) -> None:
    """Replace the stored config, carrying the *keep* keys over from the row.

    The kept values are read inside the UPDATE itself, so a key committed by a
    concurrent writer is preserved rather than reverted to an earlier read.
    """
    params: Dict[str, Any] = {"chat_id": chat_id, "config": json.dumps(config)}
    kept = []
    for index, key in enumerate(keep):
        params[f"keep_{index}"] = key
        params[f"path_{index}"] = _config_path(key)
        kept.append(f":keep_{index}, json(({_STORED_CONFIG_SQL}) -> :path_{index})")
    expression = "json(:config)"
    if kept:
        # json_patch drops keys whose patch value is null, so a kept key that is
        # absent from the row stays absent instead of becoming null.
        expression = f"json_patch(json(:config), json_object({', '.join(kept)}))"
    session.execute(
        text(f"UPDATE chats SET config = {expression} WHERE id = :chat_id"), params
    )


class ChatOperationsMixin:
    def clone_chat_to_point(
        self,
        source_chat_id: str,
        new_title: Optional[str] = None,
        up_to_message_index: Optional[int] = None,
    ) -> str:
        """Clone a chat, optionally truncating its display messages."""
        source = self.get_chat(source_chat_id)
        if source is None:
            raise ValueError(f"Chat not found: {source_chat_id}")
        messages = list(source.messages or [])
        if up_to_message_index is not None:
            if not 0 <= up_to_message_index <= len(messages):
                raise ValueError("up_to_message_index is outside the message history")
            messages = messages[:up_to_message_index]
        return self.create_chat(
            title=new_title or f"{source.title} (fork)",
            config=_reusable_chat_config(source.config),
            messages=messages,
            agent_state=source.agent_state if up_to_message_index is None else None,
            working_directory=source.working_directory,
            context_usage=dict(source.context_usage or {}),
            project_id=source.project_id,
        )

    def create_chat(
        self,
        title: str,
        config: Dict[str, Any],
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
        chat_id: str = None,
        working_directory: str = None,
        context_usage: Dict[str, Any] = None,
        project_id: str = None,
    ) -> str:
        """Create a new chat and return its ID."""
        now = datetime.now()
        chat_id = chat_id or str(uuid.uuid4())

        # Default to the default project if none specified
        if project_id is None:
            default = self.get_project_by_slug(self.DEFAULT_PROJECT_SLUG)
            if default:
                project_id = default.id

        chat = ChatModel(
            id=chat_id,
            title=title,
            created_at=now,
            updated_at=now,
            config=_with_message_summary(config, messages),
            messages=messages or [],
            context_usage=context_usage or {},
            agent_state=agent_state,
            working_directory=working_directory,
            project_id=project_id,
        )

        with self._session() as session:
            session.add(chat)
            self._reindex_in_session(session, chat_id, messages or [])
            self.commit_chat_changes(session, [chat_id], created=True)
        return chat_id

    def get_chat(self, chat_id: str) -> Optional[ChatModel]:
        """Get a specific chat by ID."""
        with self._session() as session:
            return session.get(ChatModel, chat_id)

    def commit_chat_changes(
        self,
        session: Session,
        chat_ids: Iterable[str],
        *,
        created: bool = False,
        checkpoint_events: Optional[Dict[str, List[tuple[str, Any]]]] = None,
    ) -> None:
        """Commit *session*, recording what it changed in *chat_ids* logs first.

        Every write to a ``chats`` row ends here instead of ``session.commit()``.
        The uncommitted rows are projected, the difference from each chat's log
        is appended and fsynced, and only then does SQLite commit. A failed
        commit takes the appended events back out; a crash in between leaves
        the log ahead of SQLite, which :meth:`reconcile_chat_logs` replays.
        *checkpoint_events* adds log-only events per chat.
        """
        session.flush()
        # Take SQLite's write lock even when the session changed nothing (an
        # import, a checkpoint update) before any chat lock, so nothing ever
        # waits for SQLite while holding a chat lock another writer needs.
        session.execute(text("UPDATE chat_log_index SET seq = seq WHERE 0"))
        ids = sorted(set(chat_ids))
        pending: List[PendingAppend] = []
        with ExitStack() as locks:
            for chat_id in ids:
                locks.enter_context(self.chat_log.lock(chat_id))
            try:
                for chat_id in ids:
                    append = self.chat_log.prepare(
                        chat_id,
                        self._project_in_session(session, chat_id),
                        created=created,
                        extra=tuple((checkpoint_events or {}).get(chat_id, ())),
                    )
                    if append is not None:
                        pending.append(append)
                        self._index_in_session(
                            session,
                            chat_id,
                            None
                            if append.projection is None
                            else (append.seq, append.size, append.mtime_ns),
                        )
                session.commit()
            except BaseException:
                session.rollback()
                for append in pending:
                    self.chat_log.undo(append)
                raise
            for append in pending:
                self.chat_log.confirm(append)

    def _project_in_session(
        self, session: Session, chat_id: str
    ) -> Optional[Projection]:
        """Project the row as *session* sees it, uncommitted changes included."""
        table = ChatModel.__table__
        row = (
            session.connection()
            .execute(sa_select(table).where(table.c.id == chat_id))
            .first()
        )
        return project_chat(row) if row is not None else None

    def _index_in_session(
        self, session: Session, chat_id: str, position: Optional[tuple[int, int, int]]
    ) -> None:
        if position is None:
            session.exec(
                delete(ChatLogIndexModel).where(ChatLogIndexModel.chat_id == chat_id)
            )
            return
        seq, size, mtime_ns = position
        session.merge(
            ChatLogIndexModel(chat_id=chat_id, seq=seq, size=size, mtime_ns=mtime_ns)
        )

    def all_chat_ids(self) -> list[str]:
        with self._session() as session:
            return list(session.exec(select(ChatModel.id)).all())

    def reconcile_chat_logs(self, *, rebuild: bool = False) -> int:
        """Replay the logs SQLite has not caught up with. Returns chats changed.

        A log is replayed when its size or mtime differs from what the index
        recorded at the last commit: events a crash kept out of SQLite, a hand
        edit, or a ``chats.db`` that was deleted and recreated empty. With
        *rebuild*, every log is replayed.
        """
        with self._session() as session:
            index = {
                entry.chat_id: (entry.size, entry.mtime_ns)
                for entry in session.exec(select(ChatLogIndexModel)).all()
            }
        changed = 0
        for chat_id in self.chat_log.chat_ids():
            if not rebuild and index.get(chat_id) == self.chat_log.stat(chat_id):
                continue
            try:
                changed += self._restore_chat_from_log(chat_id)
            except Exception as exc:
                logger.warning("Could not replay the log of chat {}: {}", chat_id, exc)
        if changed:
            logger.info("Replayed {} chat logs into chats.db", changed)
        self.chat_log.purge_trash()
        return changed

    def _restore_chat_from_log(self, chat_id: str) -> int:
        """Make the row match its log. Returns 1 if the row changed."""
        with self.chat_log.lock(chat_id):
            self.chat_log.forget(chat_id)
            logged, seq = self.chat_log.logged(chat_id)
            if seq == 0:
                # Unreadable and set aside, or holding no complete event: the
                # row is the only copy, and its next write starts a new log.
                self.chat_log.path(chat_id).unlink(missing_ok=True)
                self.chat_log.forget(chat_id)
                return 0
        with self._session() as session:
            stored = self._project_in_session(session, chat_id)
            if logged is None:
                if stored is not None:
                    self._delete_chat_rows(session, [chat_id])
                self._index_in_session(session, chat_id, None)
                session.commit()
                self.chat_log.retire(chat_id)
                return int(stored is not None)
            differs = bool(projection_differences(logged, stored))
            if differs:
                self._write_projection(session, chat_id, logged)
            size, mtime_ns = self.chat_log.stat(chat_id)
            self._index_in_session(session, chat_id, (seq, size, mtime_ns))
            self.commit_chat_changes(session, [chat_id])
        return int(differs)

    def _write_projection(
        self, session: Session, chat_id: str, projection: Projection
    ) -> None:
        """Overwrite (or create) a chat's row from its logged projection."""
        chat = session.get(ChatModel, chat_id)
        created_at = datetime.fromisoformat(projection["created_at"])
        if chat is None:
            chat = ChatModel(
                id=chat_id, title="", created_at=created_at, updated_at=created_at
            )
        project_id = projection["project_id"]
        if project_id and session.get(ProjectModel, project_id) is None:
            # Projects live only in chats.db; a chat whose project is gone
            # lands in the default project, and the move is logged.
            default = self.get_project_by_slug(self.DEFAULT_PROJECT_SLUG)
            project_id = default.id if default else None
        last_active_at = projection["last_active_at"]
        chat.title = projection["title"]
        chat.pinned = projection["pinned"]
        chat.project_id = project_id
        chat.working_directory = projection["working_directory"]
        chat.created_at = created_at
        chat.updated_at = datetime.fromisoformat(projection["updated_at"])
        chat.last_active_at = (
            datetime.fromisoformat(last_active_at) if last_active_at else None
        )
        chat.turn_count = projection["turn_count"]
        chat.context_usage = copy.deepcopy(projection["context_usage"])
        chat.config = copy.deepcopy(projection["config"])
        chat.messages = copy.deepcopy(projection["messages"])
        chat.agent_state = state_bytes(projection["state"])
        for column in ("context_usage", "config", "messages"):
            flag_modified(chat, column)
        session.add(chat)
        self._reindex_in_session(session, chat_id, chat.messages)

    def import_unlogged_chats(self) -> int:
        """Start a log for every chat without one. Returns how many were started.

        Chats written before logs existed get a ``chat.imported`` snapshot, and
        their retry checkpoints move out of the old ``retry_checkpoints`` table.
        """
        logged = set(self.chat_log.chat_ids())
        imported = 0
        for chat_id in self.all_chat_ids():
            if chat_id in logged:
                continue
            try:
                with self._session() as session:
                    self.commit_chat_changes(session, [chat_id])
                imported += 1
            except Exception as exc:
                logger.warning("Could not start a log for chat {}: {}", chat_id, exc)
        self._import_legacy_retry_checkpoints()
        if imported:
            logger.info("Started JSONL logs for {} existing chats", imported)
        return imported

    def _import_legacy_retry_checkpoints(self) -> None:
        with self.engine.connect() as connection:
            if not sa_inspect(connection).has_table("retry_checkpoints"):
                return
            rows = (
                connection.execute(text("SELECT * FROM retry_checkpoints"))
                .mappings()
                .all()
            )
        for row in rows:
            chat_id = row["chat_id"]
            if self.get_retry_checkpoint(chat_id) is not None:
                continue
            config_snapshot = _json_column(row["config_snapshot"], {})
            self.save_retry_checkpoint(
                chat_id,
                checkpoint_id=config_snapshot.get("_retry_checkpoint_id")
                or uuid.uuid4().hex,
                agent_state_before=row["agent_state_before"],
                messages_before=_json_column(row["messages_before"], []),
                user_message=row["user_message"] or "",
                user_files=_json_column(row["user_files"], []),
                config_snapshot=config_snapshot,
                file_snapshot=_json_column(row["file_snapshot"], [])
                if row["has_file_snapshot"]
                else None,
            )
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE retry_checkpoints"))
        logger.info("Moved {} retry checkpoints into chat logs", len(rows))

    # -------------------------------------------------------------------------
    # Retry checkpoints
    # -------------------------------------------------------------------------

    def save_retry_checkpoint(
        self,
        chat_id: str,
        *,
        checkpoint_id: str,
        agent_state_before: Optional[bytes],
        messages_before: List[Dict[str, Any]],
        user_message: str,
        user_files: List[Any],
        config_snapshot: Dict[str, Any],
        file_snapshot: Optional[List[Any]] = None,
    ) -> bool:
        """Record the state a retry of the coming turn rewinds to.

        When that state is the chat as stored, the checkpoint names the log
        position instead of carrying a copy, so a checkpoint per turn costs a
        few hundred bytes rather than the whole conversation.
        """
        with self._session() as session:
            # Hold SQLite's write lock so the row cannot move between the
            # comparison below and the checkpoint's position in the log.
            claimed = session.execute(
                update(ChatModel).where(ChatModel.id == chat_id).values(id=ChatModel.id)
            )
            if claimed.rowcount != 1:
                return False
            current = self._project_in_session(session, chat_id)
            before_messages = visible_messages(messages_before)
            before_state = project_state(agent_state_before)
            if before_messages == current["messages"] and (
                before_state == current["state"]
            ):
                before: Dict[str, Any] = {"seq": None}
            else:
                before = {"messages": before_messages, "state": before_state}
            checkpoint = normalize_json(
                {
                    "id": checkpoint_id,
                    "user_message": user_message,
                    "user_files": list(user_files),
                    "config_snapshot": dict(config_snapshot),
                    "has_file_snapshot": file_snapshot is not None,
                    "file_snapshot": list(file_snapshot or []),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            checkpoint["before"] = before
            self.commit_chat_changes(
                session,
                [chat_id],
                checkpoint_events={chat_id: [("checkpoint.set", checkpoint)]},
            )
        return True

    def get_retry_checkpoint(self, chat_id: str) -> Optional[RetryCheckpoint]:
        with self.chat_log.lock(chat_id):
            projection, _ = self.chat_log.logged(chat_id)
            checkpoint = (projection or {}).get("checkpoint")
            if checkpoint is None:
                return None
            return RetryCheckpoint.from_logged(
                chat_id, copy.deepcopy(checkpoint), self.chat_log
            )

    def update_retry_checkpoint(
        self, chat_id: str, checkpoint_id: str, fields: Dict[str, Any]
    ) -> bool:
        """Change fields of the chat's checkpoint if it is still *checkpoint_id*."""
        checkpoint = self.get_retry_checkpoint(chat_id)
        if checkpoint is None or checkpoint.id != checkpoint_id:
            return False
        update_event = ("checkpoint.update", {"id": checkpoint_id, "set": fields})
        with self._session() as session:
            self.commit_chat_changes(
                session, [chat_id], checkpoint_events={chat_id: [update_event]}
            )
        return True

    def record_turn_file_changes(
        self, chat_id: str, file_snapshot: List[Dict[str, Any]]
    ) -> None:
        """Attach a finished turn's file changes to its checkpoint and its answer."""
        checkpoint = self.get_retry_checkpoint(chat_id)
        events: List[tuple[str, Any]] = []
        if checkpoint is not None:
            fields = {"file_snapshot": file_snapshot, "has_file_snapshot": True}
            events.append(("checkpoint.update", {"id": checkpoint.id, "set": fields}))
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if chat is not None and file_snapshot:
                display_messages = list(chat.messages or [])
                assistant_index = next(
                    (
                        index
                        for index in range(len(display_messages) - 1, -1, -1)
                        if isinstance(display_messages[index], dict)
                        and display_messages[index].get("role") == "assistant"
                    ),
                    None,
                )
                if assistant_index is not None:
                    assistant = dict(display_messages[assistant_index])
                    assistant["file_changes"] = file_snapshot
                    display_messages[assistant_index] = assistant
                    chat.messages = display_messages
                    flag_modified(chat, "messages")
                    session.add(chat)
            self.commit_chat_changes(
                session, [chat_id], checkpoint_events={chat_id: events}
            )

    def chat_log_differences(self, chat_log: ChatEventLog) -> dict[str, list[str]]:
        """Fold every log in *chat_log* and compare it with the stored row.

        Returns the chats that disagree, each with the fields that differ. A row
        with no log, or a log with no row, is reported too.
        """
        report: dict[str, list[str]] = {}
        for chat_id in sorted(set(self.all_chat_ids()) | set(chat_log.chat_ids())):
            chat = self.get_chat(chat_id)
            try:
                logged, _ = chat_log.fold(chat_id)
            except ChatLogError as exc:
                report[chat_id] = [f"<unreadable log: {exc}>"]
                continue
            differences = projection_differences(
                logged, project_chat(chat) if chat else None
            )
            if differences:
                report[chat_id] = differences
        return report

    def ensure_channel_chat(
        self,
        chat_id: str,
        title: str,
        platform: str,
        config_extra: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Create the chat row for an inbound channel session if missing.

        Channel chats (Telegram/Discord/Suzent peers) share the same shape: a
        ``platform`` tag so they classify as social, and placement in the Social
        project. Callers pass their own title and any extra config (sender ids).
        Returns True if a row was created, False if it already existed.
        """
        if self.get_chat(chat_id) is not None:
            return False
        social_project = self.get_project_by_slug(self.SOCIAL_PROJECT_SLUG)
        config: Dict[str, Any] = {"platform": platform}
        if config_extra:
            config.update(config_extra)
        self.create_chat(
            title=title,
            config=config,
            chat_id=chat_id,
            project_id=social_project.id if social_project else None,
        )
        return True

    def update_chat(
        self,
        chat_id: str,
        title: str = None,
        config: Dict[str, Any] = None,
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
        working_directory: str = None,
        context_usage: Dict[str, Any] = None,
        reindex: bool = True,
        pinned: bool | None = None,
    ) -> bool:
        """Update an existing chat.

        ``reindex=False`` skips the full-text reindex. The reindex rewrites every
        FTS row for the chat, so it costs time proportional to the whole
        conversation — fine for a turn that has landed, ruinous for a write that
        repeats every fraction of a second. Use it only for transient writes that
        a later write will supersede (the streaming draft), never for content
        that must be findable.
        """
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            if pinned is not None:
                chat.pinned = pinned

            should_update_timestamp = False

            if title is not None and title != chat.title:
                chat.title = title
                should_update_timestamp = True

            if config is not None:
                next_config = dict(config)
                # UI config snapshots must not erase or resurrect server-owned approvals.
                next_config.pop("_pending_approvals", None)
                keep = ["_pending_approvals"]
                if messages is None:
                    keep += [
                        key
                        for key in (SUMMARY_VISIBLE_COUNT_KEY, SUMMARY_LAST_MESSAGE_KEY)
                        if key not in next_config
                    ]
                _replace_config(session, chat_id, next_config, keep)

            if messages is not None:
                chat.messages = messages
                _set_config_keys(session, chat_id, _message_summary(messages))
                should_update_timestamp = True

            if context_usage is not None:
                chat.context_usage = context_usage
                flag_modified(chat, "context_usage")

            if agent_state is not None:
                chat.agent_state = agent_state
                should_update_timestamp = True

            if working_directory is not None:
                chat.working_directory = working_directory

            if should_update_timestamp:
                chat.updated_at = datetime.now()

            session.add(chat)
            if messages is not None and reindex:
                self._reindex_in_session(session, chat_id, messages)
            if messages is not None and not reindex:
                # A streaming draft: the log leaves it out, and the turn's
                # real write records the summary and timestamp it changes.
                session.commit()
            else:
                self.commit_chat_changes(session, [chat_id])
        return True

    def append_chat_message(self, chat_id: str, message: Dict[str, Any]) -> bool:
        """Append one display message to a chat."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            messages = list(chat.messages or [])
            messages.append(message)
            chat.messages = messages
            _set_config_keys(session, chat_id, _message_summary(messages))
            chat.updated_at = datetime.now()
            session.add(chat)
            self._reindex_in_session(session, chat_id, messages)
            self.commit_chat_changes(session, [chat_id])
        return True

    def append_voice_log(
        self, chat_id: str, entries: List[Dict[str, Any]], limit: int = 1000
    ) -> bool:
        """Append realtime voice transcript rows, replacing rows with the same id."""
        if not entries:
            return True
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False
            log = [row for row in (chat.voice_log or []) if isinstance(row, dict)]
            index = {row.get("id"): i for i, row in enumerate(log)}
            for entry in entries:
                position = index.get(entry.get("id"))
                if position is None:
                    index[entry.get("id")] = len(log)
                    log.append(dict(entry))
                else:
                    log[position] = dict(entry)
            chat.voice_log = log[-limit:]
            session.add(chat)
            session.commit()
        return True

    def append_chat_message_once(
        self, chat_id: str, message: Dict[str, Any], client_message_id: str
    ) -> str:
        """Append a client-authored message once, returning its claim status."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return "missing"

            messages = list(chat.messages or [])
            if any(
                isinstance(item, dict)
                and item.get("_client_message_id") == client_message_id
                for item in messages
            ):
                return "duplicate"

            entry = dict(message)
            entry["_client_message_id"] = client_message_id
            messages.append(entry)
            chat.messages = messages
            _set_config_keys(session, chat_id, _message_summary(messages))
            chat.updated_at = datetime.now()
            session.add(chat)
            self._reindex_in_session(session, chat_id, messages)
            self.commit_chat_changes(session, [chat_id])
        return "created"

    def has_client_message(self, chat_id: str, client_message_id: str) -> bool:
        """Return whether a chat already contains a mobile send receipt."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False
            return any(
                isinstance(item, dict)
                and item.get("_client_message_id") == client_message_id
                for item in (chat.messages or [])
            )

    def rewrite_chat_messages(
        self,
        chat_id: str,
        messages: List[Dict[str, Any]],
        agent_state: Any = _UNSET,
        turn_count_delta: int = 0,
        expected_revision: Optional[int] = None,
    ) -> bool:
        """Replace a chat's full message list, keeping derived state consistent.

        Unlike a raw ``chat.messages = ...`` assignment, this refreshes the sidebar
        summary (visible count + preview) and the FTS index so they never go stale —
        which is exactly what rollback paths (retry, heartbeat) previously skipped.

        Args:
            agent_state: When supplied, restored as-is — including ``None``, which is a
                legitimate value for a checkpoint taken before any state was serialized
                (e.g. the first turn). Omit it (the ``_UNSET`` default) to leave the
                stored state untouched, as the heartbeat rollback does.
            turn_count_delta: Added to ``turn_count`` (e.g. -1 for a heartbeat rollback).
        """
        with self._session() as session:
            if agent_state is not _UNSET:
                claim = update(ChatModel).where(ChatModel.id == chat_id)
                if expected_revision is not None:
                    claim = claim.where(ChatModel.state_revision == expected_revision)
                result = session.execute(
                    claim.values(state_revision=ChatModel.state_revision + 1)
                )
                if result.rowcount != 1:
                    return False
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            chat.messages = messages
            _set_config_keys(session, chat_id, _message_summary(messages))
            flag_modified(chat, "messages")
            if agent_state is not _UNSET:
                chat.agent_state = agent_state
            if turn_count_delta:
                chat.turn_count = max(0, (chat.turn_count or 0) + turn_count_delta)
            self._reindex_in_session(session, chat_id, messages)
            session.add(chat)
            self.commit_chat_changes(session, [chat_id])
        return True

    def merge_chat_config(self, chat_id: str, updates: Dict[str, Any]) -> bool:
        """Atomically merge top-level keys into a chat's config.

        Use this instead of ``update_chat(config=...)`` when only specific keys
        change, so concurrent writers to *other* config keys (e.g. one writing
        ``tool_approval_policy`` while another writes ``_pending_approvals``) don't
        clobber each other via a full-config replace.
        """
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            _set_config_keys(session, chat_id, updates)
            chat.updated_at = datetime.now()
            session.add(chat)
            self.commit_chat_changes(session, [chat_id])
        return True

    def commit_snapshot_state(
        self,
        chat_id: str,
        agent_state: bytes,
        append_display_messages: Optional[List[Dict[str, Any]]] = None,
        draft_run_id: Optional[str] = None,
        streamed_message: Optional[dict[str, Any]] = None,
        expected_revision: Optional[int] = None,
    ) -> Optional[int]:
        """Commit fast snapshot state and increment revision atomically.

        *append_display_messages* are display rows that must become durable at
        the same instant as the history they describe. A reminder-only turn is
        the case that needs it: its provenance cannot be reconstructed later,
        because the reminder block stops being authenticatable once the process
        restarts. Writing those rows separately loses the race — either the
        process exits between the two writes, or a stale finalizer replaces
        `messages` wholesale afterwards. Inside this transaction, the row and
        the revision advance together, so a finalizer holding an older revision
        can no longer overwrite them.

        Returns:
            The new revision, or None if the chat is missing or the expected
            revision no longer matches.
        """
        now = datetime.now()
        with self._session() as session:
            if expected_revision is not None:
                claimed = session.execute(
                    update(ChatModel)
                    .where(
                        ChatModel.id == chat_id,
                        ChatModel.state_revision == expected_revision,
                    )
                    .values(state_revision=ChatModel.state_revision)
                )
                if claimed.rowcount != 1:
                    return None
            chat = session.get(ChatModel, chat_id)
            if not chat:
                _postprocess_metrics.snapshot_failed += 1
                return None

            appended_messages: Optional[List[Dict[str, Any]]] = None
            if append_display_messages:
                existing = list(chat.messages or [])
                added = [
                    row
                    for row in append_display_messages
                    if row and row not in existing
                ]
                if added:
                    # Before any trailing assistant rows, not at the end. By the
                    # time this runs, streaming has already flushed the turn's
                    # draft as the last stored message, so appending would order
                    # the trigger after the answer it prompted — and in the exact
                    # recovery case this exists for, that ordering is what the
                    # reloaded transcript keeps.
                    # Step over the trailing row only when it is *this* run's
                    # streaming draft. A plain role check is not enough: a run
                    # cancelled or failed before emitting any draft leaves the
                    # previous turn's answer last, and inserting ahead of that
                    # corrupts the chronology this placement exists to fix. The
                    # draft records the run that wrote it, so ask rather than
                    # infer from position.
                    cut = len(existing)
                    if cut and _is_draft_of_run(existing[cut - 1], draft_run_id):
                        cut -= 1
                    appended_messages = existing[:cut] + added + existing[cut:]
                    chat.messages = appended_messages
                    flag_modified(chat, "messages")
                    # This is now a durable content write, so it owes the same
                    # derived state as update_chat: without these, a search for
                    # the trigger misses the chat and the sidebar preview stays
                    # on the previous message whenever post-processing never runs.
                    _set_config_keys(
                        session, chat_id, _message_summary(appended_messages)
                    )

            if streamed_message is not None:
                from suzent.core.display_log import merge_streamed_message

                appended_messages = merge_streamed_message(
                    list(chat.messages or []), streamed_message
                )
                chat.messages = appended_messages
                flag_modified(chat, "messages")
                _set_config_keys(session, chat_id, _message_summary(appended_messages))

            next_revision = (chat.state_revision or 0) + 1
            chat.agent_state = agent_state
            chat.state_revision = next_revision
            chat.state_stage = "snapshot"
            chat.state_updated_at = now
            chat.updated_at = now

            session.add(chat)
            if appended_messages is not None:
                self._reindex_in_session(session, chat_id, appended_messages)
            self.commit_chat_changes(session, [chat_id])
        _postprocess_metrics.snapshot_committed += 1
        return next_revision

    def append_display_rows(self, chat_id: str, rows: List[Dict[str, Any]]) -> bool:
        """Append rows the display log needs now, and advance the revision.

        For a turn's opening rows written before the turn ends. Advancing the
        revision in the same transaction stops the previous turn's finalizer,
        still holding the older revision, from replacing ``messages`` and
        deleting them. Rows already at the tail are skipped.

        Returns:
            True when the chat exists.
        """
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False
            existing = list(chat.messages or [])
            added = [row for row in rows if row not in existing[-len(rows) :]]
            if not added:
                return True
            messages = existing + added
            chat.messages = messages
            flag_modified(chat, "messages")
            _set_config_keys(session, chat_id, _message_summary(messages))
            chat.state_revision = (chat.state_revision or 0) + 1
            chat.updated_at = datetime.now()
            session.add(chat)
            self._reindex_in_session(session, chat_id, messages)
            self.commit_chat_changes(session, [chat_id])
        return True

    def finalize_state_if_revision_matches(
        self,
        chat_id: str,
        expected_revision: int,
        agent_state: bytes,
        messages: Optional[List[Dict[str, Any]]] = None,
        update_lifecycle: bool = True,
    ) -> bool:
        """Finalize chat state only when revision matches expected value.

        Returns:
            True when finalized commit succeeds, False when stale/not found.
        """
        now = datetime.now()
        with self._session() as session:
            # Claim the revision before reading so replay cannot race finalization.
            result = session.execute(
                update(ChatModel)
                .where(
                    ChatModel.id == chat_id,
                    ChatModel.state_revision == expected_revision,
                )
                .values(state_revision=expected_revision)
            )
            if result.rowcount != 1:
                return False
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            current_revision = chat.state_revision or 0
            if current_revision != expected_revision:
                return False

            chat.agent_state = agent_state
            if messages is not None:
                chat.messages = messages
                _set_config_keys(session, chat_id, _message_summary(messages))
                self._reindex_in_session(session, chat_id, messages)
            chat.finalized_revision = expected_revision
            chat.state_stage = "finalized"
            chat.state_updated_at = now
            chat.updated_at = now

            if update_lifecycle:
                chat.last_active_at = now
                chat.turn_count = (chat.turn_count or 0) + 1
                session.execute(
                    text(
                        "UPDATE chats SET config = json_set("
                        f"{_STORED_CONFIG_SQL}, '$.unread_count', "
                        "COALESCE(json_extract(config, '$.unread_count'), 0) + 1"
                        ") WHERE id = :chat_id"
                    ),
                    {"chat_id": chat_id},
                )

            session.add(chat)
            self.commit_chat_changes(session, [chat_id])
        return True

    def delete_chat(self, chat_id: str, cascade_subagents: bool = False) -> bool:
        """Delete a chat by ID. Optionally cascade-delete subagent children."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            deleted_ids = [chat_id]
            if cascade_subagents:
                all_chats = session.exec(select(ChatModel)).all()
                deleted_ids += [
                    c.id for c in all_chats if self._is_subagent_child(c, {chat_id})
                ]

            self._delete_chat_rows(session, deleted_ids)
            self.commit_chat_changes(session, deleted_ids)
        return True

    def _delete_chat_rows(self, session: Session, chat_ids: List[str]) -> None:
        """Delete chats with their suggestions, status and search rows, uncommitted."""
        for chat_id in chat_ids:
            chat = session.get(ChatModel, chat_id)
            if chat is not None:
                session.delete(chat)
            self._remove_from_fts_in_session(session, chat_id)
        session.exec(
            delete(InputSuggestionModel).where(
                col(InputSuggestionModel.chat_id).in_(chat_ids)
            )
        )
        session.exec(
            delete(ChatStatusModel).where(col(ChatStatusModel.chat_id).in_(chat_ids))
        )

    def _reindex_in_session(self, session, chat_id: str, messages) -> None:
        """Reindex a chat's FTS rows inside an open SQLModel session/transaction.

        Runs on the session's SQLAlchemy Connection so it shares the chat write's
        transaction. No-op (logged) if FTS is unavailable — search must never break
        a chat write.
        """
        try:
            if not self.fts_available():
                return
            self._reindex_chat_fts(session.connection(), chat_id, messages or [])
        except Exception as exc:
            from suzent.logger import get_logger

            get_logger(__name__).warning(
                "Inline FTS reindex failed for chat {}: {}", chat_id, exc
            )

    def _search_fts_ids(self, search):
        """Return FTS-matched chat ids for a chat-list search, or None to use LIKE.

        None means "FTS can't serve this" (no search term, FTS unavailable, or query
        below the trigram minimum) — callers then fall back to the LIKE message scan,
        preserving prior behaviour (e.g. 2-char CJK substrings).
        """
        if not search:
            return None
        return self.fts_match_chat_ids(search)

    def _remove_from_fts_in_session(self, session, chat_id: str) -> None:
        """Delete a chat's FTS rows inside an open session/transaction."""
        try:
            if not self.fts_available():
                return
            from suzent.database.search import FTS_TABLE

            session.connection().exec_driver_sql(
                f"DELETE FROM {FTS_TABLE} WHERE chat_id = ?", (chat_id,)
            )
        except Exception as exc:
            from suzent.logger import get_logger

            get_logger(__name__).warning(
                "Inline FTS delete failed for chat {}: {}", chat_id, exc
            )

    def set_last_result_at(self, chat_id: str) -> None:
        """Mark that a background executor just completed a turn for this chat."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if chat:
                chat.last_result_at = datetime.now(timezone.utc)
                session.add(chat)
                session.commit()

    def mark_chat_read(self, chat_id: str) -> None:
        """Reset unread count to zero when the user views a chat."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return
            _set_config_keys(session, chat_id, {"unread_count": 0})
            self.commit_chat_changes(session, [chat_id])

    def get_chat_projects(
        self, chat_ids: list[str]
    ) -> dict[str, tuple[str | None, str | None]]:
        """Read navigation metadata only for already-authorized conversations."""
        if not chat_ids:
            return {}
        with self._session() as session:
            rows = session.exec(
                select(ChatModel.id, ChatModel.project_id, ProjectModel.name)
                .outerjoin(ProjectModel, ChatModel.project_id == ProjectModel.id)
                .where(ChatModel.id.in_(chat_ids))
            ).all()
            return {row[0]: (row[1], row[2]) for row in rows}

    def get_pinned_chat_ids(self, chat_ids: list[str]) -> set[str]:
        if not chat_ids:
            return set()
        with self._session() as session:
            statement = select(ChatModel.id).where(
                ChatModel.id.in_(chat_ids), ChatModel.pinned
            )
            return set(session.exec(statement).all())

    def list_chat_titles(
        self, chat_ids: list[str] | None = None, limit: int = 1000
    ) -> list[tuple[str, str]]:
        """Read a scoped title index without loading transcripts or checkpoints."""
        if chat_ids == []:
            return []
        with self._session() as session:
            statement = select(ChatModel.id, ChatModel.title)
            if chat_ids is not None:
                statement = statement.where(ChatModel.id.in_(chat_ids))
            else:
                statement = _apply_chat_filters(statement, None, None, None)
            statement = statement.order_by(ChatModel.updated_at.desc()).limit(limit)
            return [(row[0], row[1]) for row in session.exec(statement).all()]

    def get_chat_navigation(
        self, chat_ids: list[str]
    ) -> dict[str, dict[str, str | None]]:
        if not chat_ids:
            return {}
        with self._session() as session:
            statement = select(ChatModel.id, ChatModel.config).where(
                ChatModel.id.in_(chat_ids)
            )
            return {
                chat_id: {
                    "platform": (config or {}).get("platform"),
                    "parentChatId": (config or {}).get("parent_chat_id"),
                }
                for chat_id, config in session.exec(statement).all()
            }

    def list_chats(
        self,
        limit: int | None = 50,
        offset: int = 0,
        search: str = None,
        platform: str = None,
        project_id: str = None,
        pinned: bool | None = None,
    ) -> List[ChatSummaryModel]:
        """List chat summaries ordered by last updated.

        Args:
            project_id: Optional filter — only return chats in this project.
            platform: Optional ``"social"`` / ``"personal"`` filter on the legacy
                ``config.platform`` field. Retained for backward compatibility;
                new code should prefer ``project_id``.
        """
        with self._session() as session:
            statement = (
                select(
                    ChatModel.id,
                    ChatModel.title,
                    ChatModel.created_at,
                    ChatModel.updated_at,
                    ChatModel.config,
                    ChatModel.last_result_at,
                    ChatModel.project_id,
                    ChatModel.pinned,
                )
                .order_by(ChatModel.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )

            if pinned is not None:
                statement = statement.where(ChatModel.pinned == pinned)

            statement = _apply_chat_filters(
                statement, search, platform, project_id, self._search_fts_ids(search)
            )

            # Build a slug/name lookup so each summary row can carry project info
            # without a per-row query.
            project_lookup: Dict[str, ProjectModel] = {
                p.id: p for p in session.exec(select(ProjectModel)).all()
            }

            results = []
            backfilled_ids: List[str] = []

            for row in session.exec(statement).all():
                (
                    chat_id,
                    title,
                    created_at,
                    updated_at,
                    config,
                    last_result_at,
                    row_project_id,
                    row_pinned,
                ) = row
                config = config or {}
                visible_count = config.get(SUMMARY_VISIBLE_COUNT_KEY)
                last_message = config.get(SUMMARY_LAST_MESSAGE_KEY)
                if visible_count is None or SUMMARY_LAST_MESSAGE_KEY not in config:
                    chat = session.get(ChatModel, chat_id)
                    messages = chat.messages if chat else []
                    visible_count, last_message = _summarize_messages(messages)
                    if chat:
                        _set_config_keys(session, chat_id, _message_summary(messages))
                        backfilled_ids.append(chat_id)

                project = project_lookup.get(row_project_id) if row_project_id else None
                results.append(
                    ChatSummaryModel(
                        id=chat_id,
                        pinned=row_pinned,
                        title=title,
                        createdAt=created_at.isoformat(),
                        updatedAt=updated_at.isoformat(),
                        messageCount=int(visible_count or 0),
                        lastMessage=last_message,
                        platform=config.get("platform"),
                        heartbeatEnabled=config.get("heartbeat_enabled", False),
                        lastResultAt=last_result_at.isoformat()
                        if last_result_at
                        else None,
                        unreadCount=config.get("unread_count", 0),
                        projectId=row_project_id,
                        projectSlug=project.slug if project else None,
                        projectName=project.name if project else None,
                        parentChatId=config.get("parent_chat_id"),
                        forkedFromChatId=config.get("forked_from_chat_id"),
                        forkedFromChatTitle=config.get("forked_from_chat_title"),
                        forkedFromMessageIndex=config.get("forked_from_message_index"),
                    )
                )

            if backfilled_ids:
                self.commit_chat_changes(session, backfilled_ids)

            return results

    def list_chats_by_config(
        self, key: str, value: Any, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Return ``{id, title, config}`` for chats whose ``config[key] == value``.

        Projects only the columns needed, so callers filtering on a config flag
        don't pull every chat's ``messages`` and ``agent_state`` blobs.
        """
        with self._session() as session:
            statement = (
                select(ChatModel.id, ChatModel.title, ChatModel.config)
                .where(ChatModel.config[key].as_string() == str(value))
                .order_by(ChatModel.updated_at.desc())
            )
            if limit is not None:
                statement = statement.limit(limit)
            return [
                {"id": row[0], "title": row[1], "config": row[2] or {}}
                for row in session.exec(statement).all()
            ]

    def get_chat_count(
        self, search: str = None, platform: str = None, project_id: str = None
    ) -> int:
        """Get total number of chats."""
        with self._session() as session:
            statement = select(func.count()).select_from(ChatModel)
            statement = _apply_chat_filters(
                statement, search, platform, project_id, self._search_fts_ids(search)
            )
            return session.exec(statement).one()

    def get_chat_kind_counts(
        self, search: str = None, platform: str = None, project_id: str = None
    ) -> Dict[str, int]:
        """Get chat totals for the sidebar kind tabs."""
        fts_ids = self._search_fts_ids(search)

        def count(extra_filter=None) -> int:
            statement = select(func.count()).select_from(ChatModel)
            statement = _apply_chat_filters(
                statement, search, platform, project_id, fts_ids
            )
            if extra_filter is not None:
                statement = statement.where(extra_filter)
            return session.exec(statement).one()

        with self._session() as session:
            scheduled_filter = text(
                "lower(json_extract(config, '$.platform')) = 'cron'"
            )
            you_filter = text(
                "(json_extract(config, '$.platform') IS NULL "
                "OR lower(json_extract(config, '$.platform')) != 'cron')"
            )
            total = count()
            scheduled = count(scheduled_filter)
            return {
                "you": count(you_filter),
                "scheduled": scheduled,
                "all": total,
            }

    def count_chats_in_project(self, project_id: str) -> int:
        """Return the number of chats currently in this project."""
        with self._session() as session:
            return session.exec(
                select(func.count())
                .select_from(ChatModel)
                .where(ChatModel.project_id == project_id)
            ).one()

    def get_active_heartbeats(self) -> List[ChatModel]:
        """Get all chats that have heartbeat enabled in their config."""
        with self._session() as session:
            statement = select(
                ChatModel.id,
                ChatModel.title,
                ChatModel.created_at,
                ChatModel.updated_at,
                ChatModel.config,
            ).where(text("json_extract(config, '$.heartbeat_enabled') = 1"))
            return [
                ChatModel(
                    id=chat_id,
                    title=title,
                    created_at=created_at,
                    updated_at=updated_at,
                    config=config or {},
                )
                for chat_id, title, created_at, updated_at, config in session.exec(
                    statement
                ).all()
            ]

    # -------------------------------------------------------------------------
    # PostProcess Job Operations
    # -------------------------------------------------------------------------
