from types import SimpleNamespace

import suzent.core.chat_processor as chat_processor
from suzent.core.chat_processor import _presave_turn_rows


class _FakeDb:
    def __init__(self, messages: list[dict]):
        self.chat = SimpleNamespace(messages=messages)
        self.writes: list[list[dict]] = []

    def get_chat(self, chat_id: str):
        return self.chat

    def update_chat(self, chat_id: str, messages: list[dict]):
        self.writes.append(messages)
        self.chat.messages = messages


def test_presave_shows_prompt_and_triggers_before_the_turn_ends(monkeypatch):
    db = _FakeDb([])
    monkeypatch.setattr(chat_processor, "get_database", lambda: db)
    trigger = {
        "role": "system_triggered",
        "content": "steer",
        "trigger_origin": "runtime",
    }

    _presave_turn_rows("subagent-x", "Investigate the bug", [trigger])

    assert db.chat.messages == [
        {"role": "user", "content": "Investigate the bug"},
        trigger,
    ]


def test_presave_is_idempotent_but_allows_a_repeated_prompt_later(monkeypatch):
    prompt = {"role": "user", "content": "again"}
    db = _FakeDb([prompt, {"role": "assistant", "content": "done"}])
    monkeypatch.setattr(chat_processor, "get_database", lambda: db)

    _presave_turn_rows("subagent-x", "again", [])
    assert db.chat.messages[-1] == prompt

    _presave_turn_rows("subagent-x", "again", [])
    assert len(db.writes) == 1


def test_presave_skips_empty_turns(monkeypatch):
    db = _FakeDb([])
    monkeypatch.setattr(chat_processor, "get_database", lambda: db)

    _presave_turn_rows("subagent-x", "  ", [])

    assert db.writes == []
