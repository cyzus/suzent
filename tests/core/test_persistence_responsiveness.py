"""Persistence must neither starve other streams nor lose a failed draft."""

import asyncio
import threading
from concurrent.futures import Future
from types import SimpleNamespace

import pytest

from suzent import streaming
from suzent.core.chat_processor import ChatProcessor


class _FlakyLive:
    """Stands in for the live-turn journal; fails the first ``fail`` records."""

    def __init__(self, fail: int = 1) -> None:
        self.fail = fail
        self.records: list[list[dict]] = []

    def publish(self, chat_id: str, message: dict) -> None:
        pass

    def record(self, chat_id: str, run_id: str, parts: list, **kwargs) -> Future:
        self.records.append(parts)
        future: Future = Future()
        if len(self.records) <= self.fail:
            future.set_exception(OSError("temporary write failure"))
        else:
            future.set_result(None)
        return future


async def test_failed_background_draft_is_retried_by_final_flush() -> None:
    live = _FlakyLive()
    acc = streaming._DraftDisplayAccumulator("test-chat", "test-run", live=live)
    acc.parts = [{"type": "text", "text": "recover this answer"}]
    acc.dirty = True
    await acc.maybe_persist()
    await acc._persist_task
    await acc.maybe_persist(force=True)
    assert len(live.records) == 2
    assert live.records[-1][0]["text"] == "recover this answer"
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


async def test_failed_forced_draft_stays_retryable() -> None:
    live = _FlakyLive()
    acc = streaming._DraftDisplayAccumulator("test-chat", "test-run", live=live)
    acc.parts = [{"type": "text", "text": "answer"}]
    acc.dirty = True
    with pytest.raises(OSError):
        await acc.maybe_persist(force=True)
    await acc.maybe_persist(force=True)
    assert len(live.records) == 2
    assert not acc.dirty


async def test_streaming_draft_is_readable_without_touching_the_row(
    temp_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes.chat_routes import _chat_payload

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.routes.chat_routes.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat(title="Draft recovery", messages=[], config={})
    revision = temp_db.get_chat(chat_id).updated_at
    acc = streaming._DraftDisplayAccumulator(chat_id, "test-run")
    acc.apply(
        SimpleNamespace(
            type="TEXT_MESSAGE_CONTENT", message_id="text-1", delta="partial answer"
        )
    )
    await acc.maybe_persist()
    await acc._persist_task

    assert temp_db.get_chat(chat_id).messages == []
    assert temp_db.get_chat(chat_id).updated_at == revision
    row = _chat_payload(chat_id, include_runtime=False)["messages"][-1]
    assert row["content"] == "partial answer"
    assert row["_streaming_run_id"] == "test-run"
    assert row["_streaming_draft"] is True
    await acc.finish("2026-01-01T00:00:00+00:00")
    assert acc.live.path(chat_id, "test-run").exists()
