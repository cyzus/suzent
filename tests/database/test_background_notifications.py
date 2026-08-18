from __future__ import annotations

from suzent.database import notifications


def test_background_notifications_survive_until_drained(temp_db):
    first_id = temp_db.create_background_notification(
        source="cron",
        title="Morning report",
        result="All systems operational",
        job_id=7,
    )
    second_id = temp_db.create_background_notification(
        source="heartbeat",
        title="Heartbeat",
        result="Action required",
    )

    notifications = temp_db.drain_background_notifications()

    assert [notification.id for notification in notifications] == [
        first_id,
        second_id,
    ]
    assert notifications[0].job_id == 7
    assert notifications[0].result == "All systems operational"
    assert all(notification.delivered_at is not None for notification in notifications)
    assert temp_db.drain_background_notifications() == []


def test_background_notification_payload_is_bounded(temp_db):
    temp_db.create_background_notification(
        source="x" * 100,
        title="y" * 500,
        result="z" * 5000,
    )

    notification = temp_db.drain_background_notifications()[0]

    assert len(notification.source) == 50
    assert len(notification.title) == 200
    assert len(notification.result) == 2000


def test_pending_notification_count_is_bounded(temp_db, monkeypatch):
    monkeypatch.setattr(notifications, "MAX_PENDING_NOTIFICATIONS", 3)
    for index in range(5):
        temp_db.create_background_notification(
            source="cron", title=f"Job {index}", result="done"
        )

    drained = temp_db.drain_background_notifications(limit=10)

    assert [item.title for item in drained] == ["Job 2", "Job 3", "Job 4"]
