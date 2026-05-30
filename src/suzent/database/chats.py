import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, text
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from .models import (
    ChatModel,
    ChatSummaryModel,
    PlanModel,
    ProjectModel,
    _postprocess_metrics,
    messages_search_filter,
)


def _apply_chat_filters(statement, search, platform, project_id):
    """Apply common search/platform/project filters to a ChatModel statement."""
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
            config=config,
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
                chat.config = config
                flag_modified(chat, "config")

            if messages is not None:
                chat.messages = messages
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
                    ChatModel.messages,
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
            import re

            for row in session.exec(statement).all():
                (
                    chat_id,
                    title,
                    created_at,
                    updated_at,
                    config,
                    messages,
                    last_result_at,
                    row_project_id,
                ) = row
                messages = messages or []
                last_message = None
                if messages:
                    last_msg = messages[-1]
                    if isinstance(last_msg, dict):
                        content = last_msg.get("content") or ""
                    else:
                        content = str(last_msg)

                    if isinstance(content, list):
                        # Extract text from list of dicts (e.g. OpenAI vision)
                        text_parts = []
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                text_parts.append(part.get("text", ""))
                            elif isinstance(part, str):
                                text_parts.append(part)
                        content = " ".join(text_parts)
                    elif not isinstance(content, str):
                        content = str(content)

                    # 1. completely eradicate any <details> tool blocks (including inner text)
                    clean_content = re.sub(
                        r"<details\b[^>]*>.*?</details>", "", content, flags=re.DOTALL
                    )
                    # 2. Strip remaining raw HTML tags
                    clean_content = re.sub(r"<[^>]+>", "", clean_content).strip()

                    last_message = clean_content[:100]
                    if len(clean_content) > 100:
                        last_message += "..."

                config = config or {}
                # Count only assistant messages that carry visible text.
                # Pure tool-call turns have role="assistant" but no text content,
                # so we exclude them to avoid inflating the unread badge.
                visible_count = sum(
                    1
                    for m in messages
                    if isinstance(m, dict)
                    and m.get("role") == "assistant"
                    and isinstance(m.get("content"), str)
                    and m["content"].strip()
                )
                project = project_lookup.get(row_project_id) if row_project_id else None
                results.append(
                    ChatSummaryModel(
                        id=chat_id,
                        title=title,
                        createdAt=created_at.isoformat(),
                        updatedAt=updated_at.isoformat(),
                        messageCount=visible_count,
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

    def reassign_plan_chat(self, old_chat_id: str, new_chat_id: str) -> int:
        """Reassign all plans from one chat_id to another."""
        if old_chat_id == new_chat_id:
            return 0

        with self._session() as session:
            statement = select(PlanModel).where(PlanModel.chat_id == old_chat_id)
            plans = session.exec(statement).all()

            for plan in plans:
                plan.chat_id = new_chat_id
                plan.updated_at = datetime.now()
                session.add(plan)

            session.commit()
            return len(plans)

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
