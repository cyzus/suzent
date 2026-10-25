"""Measure work while excluding overlapping waits for human input."""

from collections.abc import Iterator
from contextlib import contextmanager
import time


class RunClock:
    def __init__(self) -> None:
        self._started = time.monotonic()
        self._paused_at: float | None = None
        self._waiters = 0
        self._waited = 0.0

    @contextmanager
    def paused(self) -> Iterator[None]:
        if self._waiters == 0:
            self._paused_at = time.monotonic()
        self._waiters += 1
        try:
            yield
        finally:
            self._waiters -= 1
            if self._waiters == 0 and self._paused_at is not None:
                self._waited += time.monotonic() - self._paused_at
                self._paused_at = None

    def elapsed(self) -> float:
        end = self._paused_at if self._paused_at is not None else time.monotonic()
        return max(0.0, end - self._started - self._waited)
