"""Tests for HeartbeatRunner interval configuration."""

from suzent.core.heartbeat import HeartbeatRunner


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
