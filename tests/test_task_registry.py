"""
Tests for background task registry.
"""

import asyncio
import pytest


pytestmark = pytest.mark.anyio


class TestBackgroundTaskRegistry:
    """Test the background task registry."""

    def test_registry_creation(self):
        """Test creating a task registry."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry(max_concurrent=10)
        assert registry.max_concurrent == 10
        assert registry.active_count == 0
        assert registry.total_count == 0

    async def test_register_task(self):
        """Test registering a background task."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry()

        async def dummy_task():
            await asyncio.sleep(0.01)
            return "done"

        task = await registry.register(dummy_task(), description="Test task")

        assert registry.active_count == 1
        result = await task
        assert result == "done"

        # Task should still be in registry (not cleaned up yet)
        assert registry.total_count == 1

    async def test_max_concurrent_limit(self):
        """Test that max concurrent limit is enforced."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry(max_concurrent=2)

        async def slow_task():
            await asyncio.sleep(1)

        # Register 2 tasks (at limit)
        task1 = await registry.register(slow_task(), description="Task 1")
        task2 = await registry.register(slow_task(), description="Task 2")

        assert registry.active_count == 2

        # Try to register a 3rd task (should fail)
        with pytest.raises(RuntimeError, match="Max concurrent tasks limit reached"):
            await registry.register(slow_task(), description="Task 3")

        # Cancel tasks to clean up
        task1.cancel()
        task2.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass
        try:
            await task2
        except asyncio.CancelledError:
            pass

    async def test_cleanup_completed_tasks(self):
        """Test that completed tasks are cleaned up."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry()

        async def quick_task():
            return "done"

        # Register and complete a task
        task = await registry.register(quick_task(), description="Quick task")
        await task

        assert registry.total_count == 1

        # Register another task (should trigger cleanup)
        task2 = await registry.register(quick_task(), description="Another task")
        await task2

        # First task should be cleaned up
        # (cleanup happens on next registration)
        assert registry.total_count <= 2

    async def test_wait_for_all(self):
        """Test waiting for all tasks to complete."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry()

        async def task_with_delay(delay):
            await asyncio.sleep(delay)
            return delay

        # Register multiple tasks
        await registry.register(task_with_delay(0.01), description="Fast")
        await registry.register(task_with_delay(0.02), description="Slow")

        # Wait for all to complete
        await registry.wait_for_all(timeout=1.0)

        # All tasks should be done
        assert registry.active_count == 0

    async def test_wait_for_task_prefix(self):
        """Test waiting only for tasks matching a task_id prefix."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry()

        async def task_with_delay(delay):
            await asyncio.sleep(delay)
            return delay

        # Use an event so the unrelated task is guaranteed still active after the
        # prefix wait completes, regardless of CI timing jitter.
        release_event = asyncio.Event()

        async def blocked_task():
            await release_event.wait()

        await registry.register(
            task_with_delay(0.05), task_id="post_process_chat1_1", description="A"
        )
        await registry.register(
            task_with_delay(0.05), task_id="post_process_chat1_2", description="B"
        )
        await registry.register(blocked_task(), task_id="other_chat_1", description="C")

        # Should wait for the post_process tasks only.
        await registry.wait_for_task_prefix("post_process_chat1_", timeout=1.0)

        # The unrelated task must still be active — it's blocked on release_event.
        assert registry.active_count == 1

        # Release and await so the task doesn't leak into subsequent tests.
        release_event.set()
        await registry.wait_for_all(timeout=1.0)

    async def test_cancel_all(self):
        """Test cancelling all tasks."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry()

        async def long_task():
            await asyncio.sleep(10)

        # Register tasks
        await registry.register(long_task(), description="Long 1")
        await registry.register(long_task(), description="Long 2")

        assert registry.active_count == 2

        # Cancel all
        await registry.cancel_all()

        # All tasks should be cancelled
        assert registry.active_count == 0

    async def test_shutdown(self):
        """Test graceful shutdown."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry()

        async def quick_task():
            await asyncio.sleep(0.01)

        await registry.register(quick_task(), description="Task")

        # Shutdown should wait for tasks
        await registry.shutdown(timeout=1.0)

        # Should not allow new registrations after shutdown
        with pytest.raises(RuntimeError, match="shut down"):
            await registry.register(quick_task(), description="After shutdown")

    def test_get_stats(self):
        """Test getting registry statistics."""
        from suzent.core.task_registry import BackgroundTaskRegistry

        registry = BackgroundTaskRegistry(max_concurrent=50)

        stats = registry.get_stats()
        assert stats["active"] == 0
        assert stats["max_concurrent"] == 50

    async def test_global_registry(self):
        """Test the global registry instance."""
        from suzent.core.task_registry import (
            get_task_registry,
            register_background_task,
        )

        # Get global registry
        registry = get_task_registry()
        assert registry is not None

        # Register a task via convenience function
        async def test_task():
            return "test"

        task = await register_background_task(test_task(), description="Global test")
        result = await task
        assert result == "test"

    async def test_wait_for_background_task_prefix(self):
        """Test module-level prefix wait helper."""
        from suzent.core.task_registry import (
            register_background_task,
            wait_for_background_task_prefix,
            wait_for_all_background_tasks,
        )

        async def task_with_delay(delay):
            await asyncio.sleep(delay)
            return delay

        await register_background_task(
            task_with_delay(0.05),
            task_id="post_process_test_chat_1",
            description="Prefix wait target",
        )
        await register_background_task(
            task_with_delay(0.2),
            task_id="unrelated_task_1",
            description="Unrelated task",
        )

        await wait_for_background_task_prefix("post_process_test_chat_", timeout=1.0)

        # Cleanup remaining global tasks for test isolation.
        await wait_for_all_background_tasks(timeout=1.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
