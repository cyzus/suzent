"""Tests for HeartbeatRunner interval configuration."""

import asyncio
from unittest.mock import patch

import pytest

from suzent.core.heartbeat import HeartbeatRunner


class TestHeartbeatInterval:
    """Tests for the set_interval method on HeartbeatRunner."""

    def test_default_interval(self):
        runner = HeartbeatRunner()
        assert runner.interval_minutes == 30

    def test_custom_initial_interval(self):
        runner = HeartbeatRunner(interval_minutes=10)
        assert runner.interval_minutes == 10

    @pytest.mark.asyncio
    async def test_set_interval_updates_value(self):
        runner = HeartbeatRunner(interval_minutes=30)
        await runner.set_interval(15)
        assert runner.interval_minutes == 15

    @pytest.mark.asyncio
    async def test_set_interval_rejects_zero(self):
        runner = HeartbeatRunner()
        with pytest.raises(ValueError, match="at least 1 minute"):
            await runner.set_interval(0)

    @pytest.mark.asyncio
    async def test_set_interval_rejects_negative(self):
        runner = HeartbeatRunner()
        with pytest.raises(ValueError, match="at least 1 minute"):
            await runner.set_interval(-5)

    @pytest.mark.asyncio
    async def test_set_interval_restarts_loop_when_running(self):
        runner = HeartbeatRunner(interval_minutes=30)
        runner._running = True
        # Create a mock task that simulates a running loop
        mock_task = asyncio.create_task(asyncio.sleep(3600))
        runner._task = mock_task

        with patch.object(runner, "_run_loop", return_value=asyncio.sleep(0)):
            await runner.set_interval(5)

        assert runner.interval_minutes == 5
        # Original task should have been cancelled
        assert mock_task.cancelled()

    @pytest.mark.asyncio
    async def test_set_interval_no_restart_when_not_running(self):
        runner = HeartbeatRunner(interval_minutes=30)
        runner._running = False
        runner._task = None

        await runner.set_interval(10)

        assert runner.interval_minutes == 10
        assert runner._task is None

    def test_get_status_includes_interval(self):
        runner = HeartbeatRunner(interval_minutes=42)
        status = runner.get_status()
        assert status["interval_minutes"] == 42
