"""
Background task registry for tracking and managing long-running tasks.

Prevents resource exhaustion by:
- Tracking all background tasks
- Enforcing max concurrent task limits
- Providing graceful shutdown
- Cleaning up completed tasks
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
from suzent.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TaskInfo:
    """Information about a tracked background task."""

    task: asyncio.Task
    task_id: str
    created_at: float = field(default_factory=time.time)
    description: str = ""


class BackgroundTaskRegistry:
    """
    Global registry for tracking background tasks.

    Provides:
    - Task lifecycle management
    - Concurrent task limits
    - Graceful shutdown
    - Automatic cleanup of completed tasks
    """

    def __init__(self, max_concurrent: int = 100):
        """
        Initialize the task registry.

        Args:
            max_concurrent: Maximum number of concurrent background tasks
        """
        self.max_concurrent = max_concurrent
        self._tasks: Dict[str, TaskInfo] = {}
        self._lock = asyncio.Lock()
        self._shutdown = False

    @property
    def active_count(self) -> int:
        """Get the number of active (not done) tasks."""
        return sum(1 for info in self._tasks.values() if not info.task.done())

    @property
    def total_count(self) -> int:
        """Get the total number of tracked tasks (including completed)."""
        return len(self._tasks)

    async def register(
        self, coro, task_id: Optional[str] = None, description: str = ""
    ) -> asyncio.Task:
        """
        Register and start a background task.

        Args:
            coro: The coroutine to run as a background task
            task_id: Optional identifier for the task (auto-generated if None)
            description: Human-readable description of what the task does

        Returns:
            The created asyncio.Task

        Raises:
            RuntimeError: If max concurrent tasks limit is reached or registry is shut down
        """
        async with self._lock:
            if self._shutdown:
                raise RuntimeError("Task registry is shut down")

            # Clean up completed tasks first
            await self._cleanup_completed()

            # Enforce concurrent limit
            if self.active_count >= self.max_concurrent:
                raise RuntimeError(
                    f"Max concurrent tasks limit reached ({self.max_concurrent}). "
                    f"Active: {self.active_count}, Total: {self.total_count}"
                )

            # Generate task ID if not provided
            if task_id is None:
                task_id = f"task_{int(time.time() * 1000)}_{id(coro)}"

            # Create and track the task
            task = asyncio.create_task(coro)
            self._tasks[task_id] = TaskInfo(
                task=task, task_id=task_id, description=description
            )

            logger.debug(
                f"Registered background task {task_id}: {description} "
                f"(Active: {self.active_count}/{self.max_concurrent})"
            )

            return task

    async def _cleanup_completed(self):
        """Remove completed tasks from the registry."""
        completed_ids = [
            task_id for task_id, info in self._tasks.items() if info.task.done()
        ]

        for task_id in completed_ids:
            info = self._tasks.pop(task_id)
            # Check for exceptions
            try:
                await info.task
            except asyncio.CancelledError:
                logger.debug(f"Background task {task_id} was cancelled")
            except Exception as e:
                logger.error(f"Background task {task_id} failed: {e}")

        if completed_ids:
            logger.debug(f"Cleaned up {len(completed_ids)} completed background tasks")

    async def wait_for_all(self, timeout: Optional[float] = None):
        """
        Wait for all registered tasks to complete.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        async with self._lock:
            if not self._tasks:
                return

            tasks = [info.task for info in self._tasks.values() if not info.task.done()]

        if not tasks:
            return

        logger.info(f"Waiting for {len(tasks)} background tasks to complete...")

        if timeout:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout)
        else:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.info("All background tasks completed")

    async def cancel_all(self):
        """Cancel all registered tasks."""
        async with self._lock:
            tasks_to_cancel = [
                (task_id, info)
                for task_id, info in self._tasks.items()
                if not info.task.done()
            ]

        if not tasks_to_cancel:
            return

        logger.info(f"Cancelling {len(tasks_to_cancel)} background tasks...")

        for task_id, info in tasks_to_cancel:
            info.task.cancel()

        # Wait for cancellations to complete
        for task_id, info in tasks_to_cancel:
            try:
                await info.task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Error cancelling task {task_id}: {e}")

        logger.info("All background tasks cancelled")

    async def shutdown(self, timeout: float = 30.0):
        """
        Gracefully shutdown the registry.

        Waits for all tasks to complete, then prevents new tasks from being registered.

        Args:
            timeout: Maximum time to wait for tasks in seconds
        """
        logger.info("Shutting down background task registry...")

        async with self._lock:
            self._shutdown = True

        try:
            await self.wait_for_all(timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Shutdown timeout after {timeout}s, cancelling remaining tasks")
            await self.cancel_all()

        logger.info("Background task registry shutdown complete")

    def get_stats(self) -> Dict:
        """Get statistics about registered tasks."""
        active = 0
        completed = 0
        failed = 0

        for info in self._tasks.values():
            if info.task.done():
                try:
                    info.task.exception()
                    completed += 1
                except asyncio.CancelledError:
                    completed += 1
                except Exception:
                    failed += 1
            else:
                active += 1

        return {
            "active": active,
            "completed": completed,
            "failed": failed,
            "total": len(self._tasks),
            "max_concurrent": self.max_concurrent,
        }


# Global registry instance
_global_registry: Optional[BackgroundTaskRegistry] = None


def get_task_registry() -> BackgroundTaskRegistry:
    """Get or create the global task registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = BackgroundTaskRegistry()
    return _global_registry


async def register_background_task(
    coro, task_id: Optional[str] = None, description: str = ""
) -> asyncio.Task:
    """
    Convenience function to register a background task.

    Args:
        coro: The coroutine to run
        task_id: Optional task identifier
        description: Human-readable description

    Returns:
        The created asyncio.Task
    """
    registry = get_task_registry()
    return await registry.register(coro, task_id, description)
