"""A vault file that never finishes reading must not freeze the process.

Cloud file providers (OneDrive, iCloud Drive) accept the ``open()`` and then block
the first ``read()`` while they hydrate the file. Read on the event loop, one such
file starved every HTTP request in the backend — /health included — until the
process was killed. Reads now get their own thread and a deadline.
"""

import asyncio
import threading
from pathlib import Path

import pytest

import suzent.memory.indexer as indexer_module
from suzent.memory.indexer import read_text_off_loop


@pytest.fixture
def wedged_path():
    """A path whose read blocks the way an unhydrated cloud file does.

    The real syscall is uninterruptible and its thread stays parked until the
    provider answers; this one gives up after a second so the suite does not pay
    for the thread the event loop waits on at shutdown. All that matters is that
    the read outlives the (much shorter) deadline under test.
    """
    released = threading.Event()

    class _WedgedPath(Path):
        _flavour = type(Path())._flavour  # type: ignore[attr-defined]

        def read_text(self, *args, **kwargs):
            released.wait(1)
            return "released after the deadline"

    try:
        yield _WedgedPath("/vault/wedged.md")
    finally:
        released.set()


@pytest.mark.asyncio
async def test_unresponsive_read_gives_up_and_returns_none(monkeypatch, wedged_path):
    monkeypatch.setattr(indexer_module, "VAULT_READ_TIMEOUT_SECONDS", 0.05)

    assert await read_text_off_loop(wedged_path) is None


@pytest.mark.asyncio
async def test_the_event_loop_keeps_serving_during_a_wedged_read(
    monkeypatch, wedged_path
):
    """The real regression: other coroutines must keep running meanwhile."""
    monkeypatch.setattr(indexer_module, "VAULT_READ_TIMEOUT_SECONDS", 0.2)

    ticks = 0

    async def _heartbeat():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.01)

    beat = asyncio.create_task(_heartbeat())
    try:
        assert await read_text_off_loop(wedged_path) is None
    finally:
        beat.cancel()

    # A read done on the loop would have blocked this to a single tick.
    assert ticks > 5


@pytest.mark.asyncio
async def test_readable_file_is_returned_verbatim(tmp_path):
    page = tmp_path / "page.md"
    page.write_text("- [goal] ship it\n", encoding="utf-8")

    assert await read_text_off_loop(page) == "- [goal] ship it\n"


@pytest.mark.asyncio
async def test_missing_file_is_reported_as_unreadable(tmp_path):
    assert await read_text_off_loop(tmp_path / "gone.md") is None
