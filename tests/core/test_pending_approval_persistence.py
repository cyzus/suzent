from types import SimpleNamespace

import pytest

import suzent.streaming as streaming


class FakeDatabase:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            config={
                "_pending_approvals": [
                    {"approvalId": "call-1", "toolCallId": "call-1"},
                    {"approvalId": "call-2", "toolCallId": "call-2"},
                ]
            }
        )

    def get_chat(self, chat_id: str):
        return self.chat if chat_id == "chat-1" else None

    def merge_chat_config(self, chat_id: str, updates: dict) -> bool:
        if chat_id != "chat-1":
            return False
        self.chat.config = {**self.chat.config, **updates}
        return True


@pytest.mark.asyncio
async def test_remove_pending_approvals_removes_only_resolved_ids(
    monkeypatch,
) -> None:
    db = FakeDatabase()
    monkeypatch.setattr(streaming, "get_database", lambda: db)

    await streaming.remove_pending_approvals("chat-1", {"call-1"})

    assert db.chat.config["_pending_approvals"] == [
        {"approvalId": "call-2", "toolCallId": "call-2"}
    ]


@pytest.mark.asyncio
async def test_remove_pending_approvals_clears_all_when_ids_are_omitted(
    monkeypatch,
) -> None:
    db = FakeDatabase()
    monkeypatch.setattr(streaming, "get_database", lambda: db)

    await streaming.remove_pending_approvals("chat-1")

    assert db.chat.config["_pending_approvals"] == []
