from types import SimpleNamespace

import pytest

from suzent.core.chat_processor import ChatProcessor


@pytest.mark.asyncio
async def test_persist_agent_state_snapshot_updates_only_agent_state(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.calls = []

        def commit_snapshot_state(self, chat_id, agent_state):
            return None

        def update_chat(self, chat_id, **kwargs):
            self.calls.append((chat_id, kwargs))

    fake_db = FakeDB()

    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: fake_db)
    monkeypatch.setattr(
        "suzent.core.chat_processor.serialize_state",
        lambda messages, model_id=None, tool_names=None: b"state-bytes",
    )

    processor = ChatProcessor()
    await processor._persist_agent_state_snapshot(
        chat_id="chat-1",
        messages=[],
        model_id="model-x",
        tool_names=["tool-a"],
    )

    assert fake_db.calls == [("chat-1", {"agent_state": b"state-bytes"})]


@pytest.mark.asyncio
async def test_process_turn_persists_snapshot_before_background_postprocess(
    monkeypatch,
):
    called = {"snapshot": 0, "register": 0}

    async def fake_wait_for_background_task_prefix(prefix, timeout=None):
        return None

    class FakeAgent:
        _model_id = "model-test"
        _tool_names = ["bash_execute"]
        _last_messages = []

    async def fake_get_or_create_agent(config):
        return FakeAgent()

    fake_deps = SimpleNamespace(
        last_messages=None,
        cancel_event=None,
        is_suspended=False,
        inline_a2ui_surfaces={},
    )

    def fake_build_agent_deps(chat_id, user_id, config):
        return fake_deps

    async def fake_stream_agent_responses(*args, **kwargs):
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "ok"}\n\n'

    async def fake_persist_snapshot(self, chat_id, messages, model_id, tool_names):
        called["snapshot"] += 1

    async def fake_register_background_task(
        coro, task_id=None, description="", allow_overflow=False
    ):
        called["register"] += 1
        coro.close()
        return None

    class FakeDB:
        def get_chat(self, chat_id):
            return None

        def commit_snapshot_state(self, chat_id, agent_state):
            return 1

    monkeypatch.setattr(
        "suzent.core.task_registry.wait_for_background_task_prefix",
        fake_wait_for_background_task_prefix,
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.get_or_create_agent", fake_get_or_create_agent
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.build_agent_deps", fake_build_agent_deps
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.stream_agent_responses", fake_stream_agent_responses
    )
    monkeypatch.setattr(
        "suzent.core.chat_processor.ChatProcessor._persist_agent_state_snapshot",
        fake_persist_snapshot,
    )
    monkeypatch.setattr(
        "suzent.core.task_registry.register_background_task",
        fake_register_background_task,
    )
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: FakeDB())

    processor = ChatProcessor()

    chunks = []
    async for chunk in processor.process_turn(
        chat_id="chat-1",
        user_id="user-1",
        message_content="hello",
    ):
        chunks.append(chunk)

    assert chunks
    assert called["snapshot"] == 1
    assert called["register"] == 1


@pytest.mark.asyncio
async def test_persist_state_skips_stale_revision_guard(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.finalize_calls = []
            self.update_calls = []

        def get_chat(self, chat_id):
            return SimpleNamespace(messages=[], turn_count=0)

        def finalize_state_if_revision_matches(
            self,
            chat_id,
            expected_revision,
            agent_state,
            messages=None,
            update_lifecycle=True,
        ):
            self.finalize_calls.append((chat_id, expected_revision, messages))
            return False

        def update_chat(self, chat_id, **kwargs):
            self.update_calls.append((chat_id, kwargs))

    fake_db = FakeDB()

    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: fake_db)
    monkeypatch.setattr(
        "suzent.core.chat_processor.serialize_state",
        lambda messages, model_id=None, tool_names=None: b"state-bytes",
    )

    processor = ChatProcessor()
    await processor._persist_state(
        chat_id="chat-1",
        messages=[],
        model_id="m",
        tool_names=[],
        user_content="u",
        agent_content="a",
        expected_revision=7,
        postprocess_job_id="job-1",
    )

    assert len(fake_db.finalize_calls) == 1
    assert fake_db.finalize_calls[0][1] == 7
    assert fake_db.update_calls == []
