"""Persistence for compaction summaries prepared in the background."""

from __future__ import annotations

from datetime import datetime, timezone

from .models import PreparedSummaryModel, chat_exists


class PreparedSummaryOperationsMixin:
    def get_prepared_summary(self, chat_id: str) -> PreparedSummaryModel | None:
        with self._session() as session:
            return session.get(PreparedSummaryModel, chat_id)

    def set_prepared_summary(
        self, chat_id: str, *, end_index: int, fingerprint: str, summary: str
    ) -> None:
        """Replace the chat's prepared summary; skipped for a deleted chat."""
        with self._session() as session:
            if not chat_exists(session, chat_id):
                return
            row = session.get(PreparedSummaryModel, chat_id) or PreparedSummaryModel(
                chat_id=chat_id,
                end_index=end_index,
                fingerprint=fingerprint,
                summary="",
            )
            row.end_index = end_index
            row.fingerprint = fingerprint
            row.summary = summary
            row.created_at = datetime.now(timezone.utc)
            session.add(row)
            session.commit()

    def delete_prepared_summary(self, chat_id: str) -> None:
        with self._session() as session:
            row = session.get(PreparedSummaryModel, chat_id)
            if row is not None:
                session.delete(row)
                session.commit()
