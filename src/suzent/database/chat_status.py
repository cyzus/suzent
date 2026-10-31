"""Persistence for where each chat stands for the user."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import col, select

from .models import ChatModel, ChatStatusModel, chat_exists


class ChatStatusOperationsMixin:
    def get_chat_status(self, chat_id: str) -> ChatStatusModel | None:
        with self._session() as session:
            return session.get(ChatStatusModel, chat_id)

    def list_chat_statuses(self, chat_ids: list[str]) -> dict[str, ChatStatusModel]:
        if not chat_ids:
            return {}
        with self._session() as session:
            rows = session.exec(
                select(ChatStatusModel).where(
                    col(ChatStatusModel.chat_id).in_(chat_ids)
                )
            ).all()
            return {row.chat_id: row for row in rows}

    def waiting_chat_ids(self) -> set[str]:
        """Chats whose last turn left the next move to the user."""
        with self._session() as session:
            return set(
                session.exec(
                    select(ChatStatusModel.chat_id).where(
                        ChatStatusModel.waiting_on_user == True  # noqa: E712
                    )
                ).all()
            )

    def list_board_chats(
        self,
        project_ids: list[str],
        *,
        active_since: datetime,
        include_ids: set[str],
    ) -> list[dict[str, Any]]:
        """Chats in *project_ids* active since *active_since*, plus *include_ids*
        and any holding a tool approval, without loading their messages."""
        if not project_ids:
            return []
        since = active_since.astimezone(timezone.utc).replace(tzinfo=None)
        holds_approval = (
            func.json_array_length(ChatModel.config, "$._pending_approvals") > 0
        )
        with self._session() as session:
            rows = session.exec(
                select(
                    ChatModel.id,
                    ChatModel.title,
                    ChatModel.updated_at,
                    ChatModel.project_id,
                    ChatModel.config,
                ).where(
                    col(ChatModel.project_id).in_(project_ids),
                    or_(
                        ChatModel.updated_at >= since,
                        col(ChatModel.id).in_(list(include_ids)),
                        holds_approval,
                    ),
                )
            ).all()
        return [
            {
                "id": chat_id,
                "title": title,
                "updated_at": updated_at,
                "project_id": project_id,
                "config": config or {},
            }
            for chat_id, title, updated_at, project_id, config in rows
        ]

    def update_chat_status(self, chat_id: str, **fields) -> ChatStatusModel | None:
        """Write *fields* onto the chat's status row, creating it when missing.

        Returns None for a chat that no longer exists, so no row outlives it.
        """
        with self._session() as session:
            if not chat_exists(session, chat_id):
                return None
            row = session.get(ChatStatusModel, chat_id) or ChatStatusModel(
                chat_id=chat_id
            )
            for key, value in fields.items():
                setattr(row, key, value)
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
            session.refresh(row)
            return row
