"""Regression: system/forked chats (dream, sub-agents) must never persist agent_state.

The dream consolidation chat is reset to a clean slate before every run. If the chat
processor persists its agent_state, a previous run's history survives — and a late
finalize from the prior run can resurrect it AFTER the next run's reset (a race). The
dream agent then wakes up carrying dozens of messages of unrelated chatter and
hallucinates "I already did this, skip", so it never consolidates and the watermark
never advances (the "redoing all the work on restart" symptom).

Invariant under test: _persist_state writes empty agent_state for system chats and real
serialized state for normal chats.
"""

import pytest

from suzent.core.chat_processor import ChatProcessor


class _FakeChat:
    def __init__(self, platform):
        self.config = {"platform": platform} if platform else {}
        self.messages = []
        self.agent_state = b"old-history"


class _FakeDB:
    def __init__(self, platform):
        self._chat = _FakeChat(platform)
        self.persisted = {}

    def get_chat(self, chat_id):
        return self._chat

    def update_chat(self, chat_id, agent_state=None, messages=None):
        self.persisted["agent_state"] = agent_state
        self.persisted["messages"] = messages


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "platform,expect_empty",
    [
        ("dream", True),
        ("subagent", True),
        ("subagent_wakeup", True),
        ("telegram", False),
        (None, False),
    ],
)
async def test_persist_state_agent_state_by_platform(
    monkeypatch, platform, expect_empty
):
    import suzent.core.chat_processor as cp

    db = _FakeDB(platform)
    monkeypatch.setattr(cp, "get_database", lambda: db)
    # Make serialization deterministic and non-empty for the "normal chat" case.
    monkeypatch.setattr(cp, "serialize_state", lambda *a, **k: b"real-state")
    monkeypatch.setattr(
        cp, "_rebuild_display_messages", lambda msgs, *a, **k: [{"role": "x"}]
    )
    monkeypatch.setattr(
        cp, "_append_inline_a2ui_surfaces", lambda rebuilt, surfaces: rebuilt
    )

    proc = ChatProcessor()
    await proc._persist_state(
        chat_id="system-dream" if platform == "dream" else "c1",
        messages=[object()],
        model_id="m",
        tool_names=[],
        user_content="hi",
        agent_content="ok",
    )

    if expect_empty:
        assert db.persisted["agent_state"] == b"", (
            f"platform={platform} must not persist agent_state"
        )
    else:
        assert db.persisted["agent_state"] == b"real-state"
