import uuid
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, text
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from .models import (
    ChatModel,
    ChatSummaryModel,
    ProjectModel,
    _postprocess_metrics,
    messages_search_filter,
)

SUMMARY_LAST_MESSAGE_KEY = "_summary_last_message"
SUMMARY_VISIBLE_COUNT_KEY = "_summary_visible_assistant_count"

# Platforms hidden from the user's chat list. Only the autonomous dream consolidation
# chat is hidden — sub-agent chats are intentionally kept visible (nested under their
# parent agent in the UI), so they are NOT excluded here.
HIDDEN_CHAT_PLATFORMS = ("dream",)


def _apply_chat_filters(statement, search, platform, project_id):
    """Apply common search/platform/project filters to a ChatModel statement.

    The hidden dream consolidation chat is always excluded from listing — it is an
    internal background agent, not a user conversation (it surfacing in the sidebar
    is the bug this fixes). Sub-agent chats remain visible by design.
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
        statement = statement.where(
            or_(
                ChatModel.title.contains(search),
                messages_search_filter(search),
            )
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


def _with_message_summary(
    config: Optional[Dict[str, Any]],
    messages: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    next_config = dict(config or {})
    visible_count, last_message = _summarize_messages(messages)
    next_config[SUMMARY_VISIBLE_COUNT_KEY] = visible_count
    next_config[SUMMARY_LAST_MESSAGE_KEY] = last_message
    return next_config


def _copy_summary_keys(
    target: Dict[str, Any], source: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    for key in (SUMMARY_VISIBLE_COUNT_KEY, SUMMARY_LAST_MESSAGE_KEY):
        if key not in target and source and key in source:
            target[key] = source[key]
    return target


class ChatOperationsMixin:
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
            session.commit()

        return chat_id

    def get_chat(self, chat_id: str) -> Optional[ChatModel]:
        """Get a specific chat by ID."""
        with self._session() as session:
            return session.get(ChatModel, chat_id)

    def update_chat(
        self,
        chat_id: str,
        title: str = None,
        config: Dict[str, Any] = None,
        messages: List[Dict[str, Any]] = None,
        agent_state: bytes = None,
        working_directory: str = None,
        context_usage: Dict[str, Any] = None,
    ) -> bool:
        """Update an existing chat."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            should_update_timestamp = False

            if title is not None and title != chat.title:
                chat.title = title
                should_update_timestamp = True

            if config is not None:
                next_config = dict(config)
                if messages is None:
                    next_config = _copy_summary_keys(next_config, chat.config)
                chat.config = next_config
                flag_modified(chat, "config")

            if messages is not None:
                chat.messages = messages
                chat.config = _with_message_summary(chat.config, messages)
                should_update_timestamp = True
                flag_modified(chat, "config")

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
            session.commit()
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
            chat.config = _with_message_summary(chat.config, messages)
            chat.updated_at = datetime.now()
            flag_modified(chat, "config")
            session.add(chat)
            session.commit()
            return True

    def merge_chat_config(self, chat_id: str, updates: Dict[str, Any]) -> bool:
        """Atomically merge top-level keys into a chat's config (read-modify-write
        inside one DB session).

        Use this instead of ``update_chat(config=...)`` when only specific keys
        change, so concurrent writers to *other* config keys (e.g. one writing
        ``tool_approval_policy`` while another writes ``_pending_approvals``) don't
        clobber each other via a full-config replace.
        """
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            next_config = dict(chat.config or {})
            next_config.update(updates)
            chat.config = next_config
            chat.updated_at = datetime.now()
            flag_modified(chat, "config")
            session.add(chat)
            session.commit()
            return True

    def commit_snapshot_state(self, chat_id: str, agent_state: bytes) -> Optional[int]:
        """Commit fast snapshot state and increment revision atomically.

        Returns:
            The new state revision if the chat exists, otherwise None.
        """
        now = datetime.now()
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                _postprocess_metrics.snapshot_failed += 1
                return None

            next_revision = (chat.state_revision or 0) + 1
            chat.agent_state = agent_state
            chat.state_revision = next_revision
            chat.state_stage = "snapshot"
            chat.state_updated_at = now
            chat.updated_at = now

            session.add(chat)
            session.commit()

        _postprocess_metrics.snapshot_committed += 1
        return next_revision

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
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            current_revision = chat.state_revision or 0
            if current_revision != expected_revision:
                return False

            chat.agent_state = agent_state
            if messages is not None:
                chat.messages = messages
                chat.config = _with_message_summary(chat.config, messages)
                flag_modified(chat, "config")
            chat.finalized_revision = expected_revision
            chat.state_stage = "finalized"
            chat.state_updated_at = now
            chat.updated_at = now

            if update_lifecycle:
                chat.last_active_at = now
                chat.turn_count = (chat.turn_count or 0) + 1
                config = dict(chat.config or {})
                config["unread_count"] = config.get("unread_count", 0) + 1
                chat.config = config
                flag_modified(chat, "config")

            session.add(chat)
            session.commit()
            return True

    def delete_chat(self, chat_id: str, cascade_subagents: bool = False) -> bool:
        """Delete a chat by ID. Optionally cascade-delete subagent children."""
        with self._session() as session:
            chat = session.get(ChatModel, chat_id)
            if not chat:
                return False

            if cascade_subagents:
                all_chats = session.exec(select(ChatModel)).all()
                for c in all_chats:
                    if self._is_subagent_child(c, {chat_id}):
                        session.delete(c)

            session.delete(chat)
            session.commit()
            return True

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
            if chat:
                config = dict(chat.config or {})
                config["unread_count"] = 0
                chat.config = config
                flag_modified(chat, "config")
                session.add(chat)
                session.commit()

    def list_chats(
        self,
        limit: int = 50,
        offset: int = 0,
        search: str = None,
        platform: str = None,
        project_id: str = None,
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
                )
                .order_by(ChatModel.updated_at.desc())
                .offset(offset)
                .limit(limit)
            )

            statement = _apply_chat_filters(statement, search, platform, project_id)

            # Build a slug/name lookup so each summary row can carry project info
            # without a per-row query.
            project_lookup: Dict[str, ProjectModel] = {
                p.id: p for p in session.exec(select(ProjectModel)).all()
            }

            results = []
            summaries_backfilled = False

            for row in session.exec(statement).all():
                (
                    chat_id,
                    title,
                    created_at,
                    updated_at,
                    config,
                    last_result_at,
                    row_project_id,
                ) = row
                config = config or {}
                visible_count = config.get(SUMMARY_VISIBLE_COUNT_KEY)
                last_message = config.get(SUMMARY_LAST_MESSAGE_KEY)
                if visible_count is None or SUMMARY_LAST_MESSAGE_KEY not in config:
                    chat = session.get(ChatModel, chat_id)
                    messages = chat.messages if chat else []
                    visible_count, last_message = _summarize_messages(messages)
                    if chat:
                        chat.config = _with_message_summary(chat.config, messages)
                        flag_modified(chat, "config")
                        session.add(chat)
                        summaries_backfilled = True

                project = project_lookup.get(row_project_id) if row_project_id else None
                results.append(
                    ChatSummaryModel(
                        id=chat_id,
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
                    )
                )

            if summaries_backfilled:
                session.commit()

            return results

    def get_chat_count(
        self, search: str = None, platform: str = None, project_id: str = None
    ) -> int:
        """Get total number of chats."""
        with self._session() as session:
            statement = select(func.count()).select_from(ChatModel)
            statement = _apply_chat_filters(statement, search, platform, project_id)
            return session.exec(statement).one()

    def get_chat_kind_counts(
        self, search: str = None, platform: str = None, project_id: str = None
    ) -> Dict[str, int]:
        """Get chat totals for the sidebar kind tabs."""

        def count(extra_filter=None) -> int:
            statement = select(func.count()).select_from(ChatModel)
            statement = _apply_chat_filters(statement, search, platform, project_id)
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
