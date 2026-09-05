from collections.abc import AsyncGenerator
from typing import Any

from suzent.core.chat_processor import ChatProcessor


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
