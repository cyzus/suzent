from collections.abc import AsyncGenerator
from typing import Any

import pytest
from types import SimpleNamespace

from suzent.core.chat_processor import ChatProcessor


@pytest.mark.parametrize(
    "message,files,reminders",
    [
        ("User task", None, None),
        ("", None, ["[Agent message from Regent] Inspect repository size"]),
        ("", [{"path": "/tmp/input.txt"}], None),
    ],
)
async def test_task_entry_points_create_retry_checkpoint(
    temp_db, monkeypatch, message, files, reminders
) -> None:
    from suzent.core.retry import load_retry_checkpoint

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: temp_db)
    chat_id = temp_db.create_chat("Task", {}, [])

    async def get_agent(config):
        return SimpleNamespace(_model_id="test-model")

    monkeypatch.setattr("suzent.core.chat_processor.get_or_create_agent", get_agent)
    monkeypatch.setattr(
        "suzent.core.chat_processor.build_agent_deps",
        lambda **_: SimpleNamespace(),
    )

    class StopBeforeModelRun(Exception):
        pass

    def stop():
        raise StopBeforeModelRun

    monkeypatch.setattr("suzent.core.model_registry.get_model_registry", stop)
    with pytest.raises(StopBeforeModelRun):
        async for _ in ChatProcessor().process_turn(
            chat_id,
            "user",
            message,
            files=files,
            system_reminders=reminders,
            config_override={"memory_enabled": False},
        ):
            pass
    checkpoint = load_retry_checkpoint(chat_id)
    assert checkpoint is not None
    assert checkpoint.user_message == message
    assert checkpoint.user_files == (files or [])
    assert checkpoint.config_snapshot["_retry_input"]["system_reminders"] == (
        reminders or []
    )


def test_retry_uses_current_model_over_checkpoint_model(monkeypatch) -> None:
    checkpoint = {
        "user_message": "Try this",
        "user_files": [{"path": "/tmp/input.txt"}],
        "config_snapshot": {
            "model": "provider/old-model",
            "thinking": "low",
            "sandbox_enabled": True,
        },
    }
    monkeypatch.setattr(
        "suzent.core.retry.apply_retry_checkpoint",
        lambda _chat_id: checkpoint,
    )

    processor = ChatProcessor()
    captured: dict[str, Any] = {}

    def capture_process_turn(**kwargs: Any) -> AsyncGenerator[str, None]:
        captured.update(kwargs)

        async def stream() -> AsyncGenerator[str, None]:
            if False:
                yield ""

        return stream()

    monkeypatch.setattr(processor, "process_turn", capture_process_turn)

    retry_stream = processor._handle_retry_command(
        chat_id="chat-1",
        user_id="user-1",
        message_content="/retry",
        config={
            "model": "provider/new-model",
            "thinking": "high",
            "memory_enabled": False,
        },
        is_social=False,
        resume_approvals=None,
        is_heartbeat=False,
    )

    assert retry_stream is not None
    assert captured["message_content"] == "Try this"
    assert captured["files"] == [{"path": "/tmp/input.txt"}]
    assert captured["config_override"] == {
        "model": "provider/new-model",
        "thinking": "high",
        "sandbox_enabled": True,
        "memory_enabled": False,
        "_user_id": "user-1",
        "_chat_id": "chat-1",
    }


def test_retry_edit_uses_edited_message_and_current_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "suzent.core.retry.apply_retry_checkpoint",
        lambda _chat_id: {
            "user_message": "Original message",
            "user_files": [],
            "config_snapshot": {"model": "provider/old-model"},
        },
    )

    processor = ChatProcessor()
    captured: dict[str, Any] = {}

    def capture_process_turn(**kwargs: Any) -> AsyncGenerator[str, None]:
        captured.update(kwargs)

        async def stream() -> AsyncGenerator[str, None]:
            if False:
                yield ""

        return stream()

    monkeypatch.setattr(processor, "process_turn", capture_process_turn)

    retry_stream = processor._handle_retry_command(
        chat_id="chat-1",
        user_id="user-1",
        message_content="/retry-edit Updated message",
        config={"model": "provider/new-model"},
        is_social=False,
        resume_approvals=None,
        is_heartbeat=False,
    )

    assert retry_stream is not None
    assert captured["message_content"] == "Updated message"
    assert captured["config_override"]["model"] == "provider/new-model"


@pytest.mark.parametrize("command", ["/retry", "/retry-edit Updated task"])
def test_retry_replays_agent_task_input(monkeypatch, command: str) -> None:
    turn_input = {
        "system_reminders": ["[Agent message from Regent] Inspect repository size"],
        "incoming_citation_sources": [{"id": "source-1"}],
        "file_mentions": [{"path": "README.md"}],
    }
    monkeypatch.setattr(
        "suzent.core.retry.apply_retry_checkpoint",
        lambda _: {
            "user_message": "",
            "user_files": [],
            "config_snapshot": {},
            "turn_input": turn_input,
        },
    )
    processor = ChatProcessor()
    captured: dict[str, Any] = {}

    def capture(**kwargs: Any) -> AsyncGenerator[str, None]:
        captured.update(kwargs)

        async def stream() -> AsyncGenerator[str, None]:
            if False:
                yield ""

        return stream()

    monkeypatch.setattr(processor, "process_turn", capture)
    processor._handle_retry_command(
        chat_id="task",
        user_id="user",
        message_content=command,
        config={},
        is_social=False,
        resume_approvals=None,
        is_heartbeat=False,
    )
    editing = command.startswith("/retry-edit")
    assert captured["message_content"] == ("Updated task" if editing else "")
    assert captured["system_reminders"] == (
        None if editing else turn_input["system_reminders"]
    )
    assert (
        captured["incoming_citation_sources"] == turn_input["incoming_citation_sources"]
    )
    assert captured["file_mentions"] == turn_input["file_mentions"]
