"""Persistence operations for notifications created while the UI is closed."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import col, delete, select

from .models import BackgroundNotificationModel

MAX_PENDING_NOTIFICATIONS = 1000


class BackgroundNotificationOperationsMixin:
    def create_background_notification(
        self,
        *,
        source: str,
        title: str,
        result: str,
        job_id: int | None = None,
    ) -> int:
        """Persist a bounded notification and return its database ID."""
        notification = BackgroundNotificationModel(
            source=source[:50],
            title=title[:200],
            result=result[:2000],
            job_id=job_id,
        )
        with self._session() as session:
            session.add(notification)
            # Delivered notifications are operational history, not permanent
            # chat data. Remove old rows during normal writes to bound storage.
            cutoff = datetime.now() - timedelta(days=30)
            session.exec(
                delete(BackgroundNotificationModel).where(
                    col(BackgroundNotificationModel.delivered_at).is_not(None),
                    BackgroundNotificationModel.delivered_at < cutoff,
                )
            )
            overflow_ids = list(
                session.exec(
                    select(BackgroundNotificationModel.id)
                    .where(col(BackgroundNotificationModel.delivered_at).is_(None))
                    .order_by(
                        BackgroundNotificationModel.created_at.desc(),
                        BackgroundNotificationModel.id.desc(),
                    )
                    .offset(MAX_PENDING_NOTIFICATIONS)
                ).all()
            )
            if overflow_ids:
                session.exec(
                    delete(BackgroundNotificationModel).where(
                        col(BackgroundNotificationModel.id).in_(overflow_ids)
                    )
                )
            session.commit()
            session.refresh(notification)
            return int(notification.id)

    def drain_background_notifications(
        self, limit: int = 50
    ) -> list[BackgroundNotificationModel]:
        """Atomically return and mark the oldest pending notifications delivered."""
        safe_limit = max(1, min(limit, 200))
        with self._session() as session:
            statement = (
                select(BackgroundNotificationModel)
                .where(col(BackgroundNotificationModel.delivered_at).is_(None))
                .order_by(
                    BackgroundNotificationModel.created_at.asc(),
                    BackgroundNotificationModel.id.asc(),
                )
                .limit(safe_limit)
            )
            notifications = list(session.exec(statement).all())
            delivered_at = datetime.now()
            for notification in notifications:
                notification.delivered_at = delivered_at
                session.add(notification)
            session.commit()
            for notification in notifications:
                session.refresh(notification)
            return notifications
