"""
Base class for singleton async "brain" services (HeartbeatRunner, SchedulerBrain, SocialBrain).

Provides:
- Module-level singleton registry via _active_instance / get_active()
- Async lifecycle: start() / stop() with a background task loop
"""

import asyncio
from typing import ClassVar, Dict, Optional, Type, TypeVar

from suzent.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound="BaseBrain")

# Global registry: class -> active instance
_registry: Dict[Type, "BaseBrain"] = {}


def get_active(cls: Type[T]) -> Optional[T]:
    """Return the active instance of a BaseBrain subclass, or None."""
    return _registry.get(cls)  # type: ignore[return-value]


class BaseBrain:
    """
    Abstract base for singleton async services that run a background task loop.

    Subclasses must implement ``_run_loop()``.
    """

    _brain_name: ClassVar[str] = "BaseBrain"

    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Register as the active instance and start the background loop."""
        _registry[type(self)] = self
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"{self._brain_name} started.")

    async def stop(self):
        """Cancel the background loop and unregister."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _registry.pop(type(self), None)
        logger.info(f"{self._brain_name} stopped.")

    async def _run_loop(self):
        """Main loop — subclasses must override."""
        raise NotImplementedError
