"""Persistence must neither starve other streams nor lose a failed draft."""

import asyncio
import threading
from types import SimpleNamespace

import pytest

from suzent import streaming
from suzent.core.chat_processor import ChatProcessor


async def test_failed_background_draft_is_retried_by_final_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writes = []

    async def flaky_write(*args, **kwargs) -> None:
        writes.append(args)
        if len(writes) == 1:
            raise OSError("temporary write failure")

    monkeypatch.setattr(streaming.asyncio, "to_thread", flaky_write)
    acc = streaming._DraftDisplayAccumulator("test-chat", "test-run")
    acc.parts = [{"type": "text", "text": "recover this answer"}]
    acc.dirty = True
    await acc.maybe_persist()
    await acc._persist_task
    await acc.maybe_persist(force=True)
    assert len(writes) == 2
    assert writes[-1][-1] == "recover this answer"
    assert not acc.dirty


async def test_final_persistence_keeps_event_loop_responsive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()
    ran_on_loop = []
    loop_thread = threading.get_ident()

    class DB:
        def get_chat(self, chat_id: str) -> SimpleNamespace:
            return SimpleNamespace(messages=[])

        def finalize_state_if_revision_matches(self, **kwargs) -> bool:
            ran_on_loop.append(threading.get_ident() == loop_thread)
            entered.set()
            assert release.wait(2), (
                "event loop could not release the database operation"
            )
            return False

    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: DB())
    monkeypatch.setattr(
        "suzent.core.chat_processor.serialize_state", lambda *a, **kw: b"state"
    )
    task = asyncio.create_task(
        ChatProcessor()._persist_state(
            chat_id="test-chat",
            messages=[],
            model_id="test",
            tool_names=[],
            user_content="question",
            agent_content="answer",
            expected_revision=1,
        )
    )
    try:
        async with asyncio.timeout(3):
            while not entered.is_set():
                await asyncio.sleep(0)
            release.set()
            await task
        assert ran_on_loop == [False]
    finally:
        release.set()
        await task


async def test_failed_forced_draft_stays_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def flaky_write(*args, **kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("temporary write failure")

    monkeypatch.setattr(streaming.asyncio, "to_thread", flaky_write)
    acc = streaming._DraftDisplayAccumulator("test-chat", "test-run")
    acc.parts = [{"type": "text", "text": "answer"}]
    acc.dirty = True
    with pytest.raises(OSError):
        await acc.maybe_persist(force=True)
    await acc.maybe_persist(force=True)
    assert calls == 2
    assert not acc.dirty


async def test_native_draft_is_readable_before_run_finishes(
    temp_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat(title="Draft recovery", messages=[], config={})
    acc = streaming._DraftDisplayAccumulator(chat_id, "test-run")
    acc.apply(
        SimpleNamespace(
            type="TEXT_MESSAGE_CONTENT", message_id="text-1", delta="partial answer"
        )
    )
    await acc.maybe_persist()
    await acc._persist_task
    row = temp_db.get_chat(chat_id).messages[-1]
    assert row["content"] == "partial answer"
    assert row["_streaming_run_id"] == "test-run"
    assert row["_streaming_draft"] is True
