from inspect import signature
from types import SimpleNamespace

import pytest

from suzent.core import focal_agent
from suzent.core.focal_agent import FOCAL_CHAT_ID, get_or_create_focal_chat
from suzent.database import ChatDatabase
from suzent.memory.memory_context import (
    DreamRoots,
    build_dream_system_prompt,
    build_lint_system_prompt,
)
from suzent.tools.agents import agent_lifecycle_tools
from suzent.tools.agents.regent_send_tool import RegentSendTool


@pytest.fixture
def db(temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch) -> ChatDatabase:
    for module in (focal_agent, agent_lifecycle_tools):
        monkeypatch.setattr(module, "get_database", lambda: temp_db)
    return temp_db


@pytest.fixture
def enqueued(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []

    def enqueue(**kwargs):
        calls.append(kwargs)
        return {"message_id": f"msg-{len(calls)}", "status": "pending"}, True

    monkeypatch.setattr("suzent.core.agent_inbox.enqueue_agent_message", enqueue)
    return calls


def _ctx(chat_id: str) -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id))


async def test_a_background_run_reaches_regent(db, enqueued) -> None:
    get_or_create_focal_chat()
    dream_chat = db.create_chat("Dream", {"platform": "dream"})

    result = await RegentSendTool().forward(
        _ctx(dream_chat), "  Three uv lessons could become a skill.  "
    )

    assert result.success, result.message
    assert enqueued == [
        {
            "sender_chat_id": dream_chat,
            "target_chat_id": FOCAL_CHAT_ID,
            "content": "Three uv lessons could become a skill.",
        }
    ]


def test_regent_is_the_only_target() -> None:
    assert list(signature(RegentSendTool.forward).parameters) == [
        "self",
        "ctx",
        "message",
    ]


def test_the_dream_reports_to_regent_but_messages_no_one_else() -> None:
    from suzent.config import CONFIG

    assert "RegentSendTool" in CONFIG.memory_dream_tools
    assert "AgentSendTool" not in CONFIG.memory_dream_tools


def test_dream_and_lint_are_told_when_to_report() -> None:
    roots = DreamRoots(memory_root="/memory", notebook_root="/notebook")

    for prompt in (build_dream_system_prompt(roots), build_lint_system_prompt(roots)):
        assert "regent_send" in prompt
        assert "Most runs send nothing" in prompt
