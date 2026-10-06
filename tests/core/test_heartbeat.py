"""Tests for HeartbeatRunner interval configuration."""

from types import SimpleNamespace

import pytest

from suzent.core.heartbeat import HeartbeatRunner, stream_controls


class TestHeartbeatInterval:
    """Tests for the polling_interval_minutes property on HeartbeatRunner."""

    def test_default_interval(self):
        runner = HeartbeatRunner()
        assert runner.polling_interval_minutes == 1

    def test_custom_initial_interval(self):
        runner = HeartbeatRunner(interval_minutes=10)
        assert runner.polling_interval_minutes == 10

    def test_get_status_includes_interval(self):
        runner = HeartbeatRunner(interval_minutes=42)
        status = runner.get_status()
        assert status["polling_interval"] == 42

    def test_active_session_status_includes_running_and_unread(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chat = SimpleNamespace(
            id="chat-1",
            title="Daily report",
            config={
                "heartbeat_interval_minutes": 30,
                "heartbeat_last_run_at": None,
                "unread_count": 3,
            },
        )
        database = SimpleNamespace(get_active_heartbeats=lambda: [chat])
        monkeypatch.setattr("suzent.core.heartbeat.get_database", lambda: database)
        monkeypatch.setitem(stream_controls, "chat-1", object())

        status = HeartbeatRunner().get_status()

        assert status["active_sessions"][0]["is_running"] is True
        assert status["active_sessions"][0]["unread_count"] == 3


class TestHeartbeatAnnounce:
    """A heartbeat alert reaches the desktop app's notification queue."""

    def _capture(self, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
        calls: list[tuple] = []
        scheduler = SimpleNamespace(
            add_notification=lambda source, result, title=None: calls.append(
                (source, result, title)
            )
        )
        monkeypatch.setattr(
            "suzent.core.scheduler.get_active_scheduler", lambda: scheduler
        )
        return calls

    def test_alert_is_queued_under_chat_title(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._capture(monkeypatch)
        db = SimpleNamespace(
            get_chat=lambda chat_id: SimpleNamespace(title="Inbox watch")
        )

        HeartbeatRunner._announce("chat-1234567890", "3 new invoices", db)

        assert calls == [("heartbeat", "3 new invoices", "Inbox watch")]

    def test_untitled_chat_falls_back_to_short_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._capture(monkeypatch)
        db = SimpleNamespace(get_chat=lambda chat_id: None)

        HeartbeatRunner._announce("chat-1234567890", "alert", db)

        assert calls == [("heartbeat", "alert", "chat-123")]
