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


@pytest.mark.asyncio
async def test_a_still_blocked_path_does_not_take_a_second_thread(
    monkeypatch, wedged_path
):
    """One wedged file costs one worker, however many passes retry it.

    The watcher re-checks unchanged files every few minutes. Starting a fresh
    read each time would abandon another thread for the same path until the
    shared executor is drained and unrelated threaded work stalls too.
    """
    monkeypatch.setattr(indexer_module, "VAULT_READ_TIMEOUT_SECONDS", 0.05)
    starts = 0
    original = type(wedged_path).read_text

    def _counted(self, *args, **kwargs):
        nonlocal starts
        starts += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(type(wedged_path), "read_text", _counted)

    for _ in range(4):
        assert await read_text_off_loop(wedged_path) is None

    assert starts == 1


@pytest.mark.asyncio
async def test_the_path_is_retried_once_the_read_completes(monkeypatch, tmp_path):
    """A finished read must free its path, or one slow file is skipped forever."""
    monkeypatch.setattr(indexer_module, "VAULT_READ_TIMEOUT_SECONDS", 5)
    page = tmp_path / "page.md"
    page.write_text("first\n", encoding="utf-8")

    assert await read_text_off_loop(page) == "first\n"
    assert await read_text_off_loop(page) == "first\n"


@pytest.mark.asyncio
async def test_a_failed_read_frees_its_path_too(monkeypatch, tmp_path):
    monkeypatch.setattr(indexer_module, "VAULT_READ_TIMEOUT_SECONDS", 5)
    missing = tmp_path / "gone.md"

    assert await read_text_off_loop(missing) is None
    missing.write_text("here now\n", encoding="utf-8")
    assert await read_text_off_loop(missing) == "here now\n"
