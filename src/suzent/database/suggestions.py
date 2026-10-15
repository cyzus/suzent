"""Persistence for the guessed next message shown in the chat box."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import ChatModel, InputSuggestionModel


class InputSuggestionOperationsMixin:
    def get_input_suggestion(self, chat_id: str) -> InputSuggestionModel | None:
        with self._session() as session:
            return session.get(InputSuggestionModel, chat_id)

    def set_input_suggestion(
        self, chat_id: str, reply_key: str, text: str | None
    ) -> None:
        """Save the chat's guess, or forget it when *text* is None.

        A chat deleted while its guess was being made is skipped, so no row
        outlives its chat.
        """
        with self._session() as session:
            row = session.get(InputSuggestionModel, chat_id)
            if text is None or session.get(ChatModel, chat_id) is None:
                if row is not None:
                    session.delete(row)
                    session.commit()
                return
            if row is None:
                row = InputSuggestionModel(
                    chat_id=chat_id, reply_key=reply_key, text=text
                )
            else:
                row.reply_key = reply_key
                row.text = text
                row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()
