"""Persistence for where each chat stands for the user."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import col, select

from .models import ChatModel, ChatStatusModel


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

    def get_chat_configs(self, chat_ids: list[str]) -> dict[str, dict]:
        """Each chat's config, without loading its messages."""
        if not chat_ids:
            return {}
        with self._session() as session:
            rows = session.exec(
                select(ChatModel.id, ChatModel.config).where(
                    col(ChatModel.id).in_(chat_ids)
                )
            ).all()
            return {chat_id: config or {} for chat_id, config in rows}

    def update_chat_status(self, chat_id: str, **fields) -> ChatStatusModel | None:
        """Write *fields* onto the chat's status row, creating it when missing.

        Returns None for a chat that no longer exists, so no row outlives it.
        """
        with self._session() as session:
            if session.get(ChatModel, chat_id) is None:
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
