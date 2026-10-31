"""Persistence for the memories retrieved on a chat's latest turn."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import MemoryRecallModel, chat_exists


class MemoryRecallOperationsMixin:
    def get_memory_recall(self, chat_id: str) -> MemoryRecallModel | None:
        with self._session() as session:
            return session.get(MemoryRecallModel, chat_id)

    def set_memory_recall(self, chat_id: str, items: list[dict[str, Any]]) -> None:
        """Replace the chat's recall with *items*; an empty list means none was used.

        A chat deleted mid-turn is skipped, so no row outlives its chat.
        """
        with self._session() as session:
            if not chat_exists(session, chat_id):
                return
            row = session.get(MemoryRecallModel, chat_id)
            if row is None:
                row = MemoryRecallModel(chat_id=chat_id, items=items)
            else:
                row.items = items
                row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
