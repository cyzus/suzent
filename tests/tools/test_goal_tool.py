from unittest.mock import MagicMock

import pytest

import suzent.tools.tasks.goal_tool as goal_tool
from suzent.config import CONFIG
from suzent.tools.tasks.goal_tool import GoalTool


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake = MagicMock()
    fake.get_goal.return_value = None
    monkeypatch.setattr(goal_tool, "get_database", lambda: fake)
    return fake


def test_set_goal_uses_configured_turn_limit(
    db: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(CONFIG, "goals_max_turns", 7)

    result = GoalTool()._set_goal("project-1", "ship it", None, chat_id="chat-1")

    assert result.success
    assert db.create_goal.call_args.kwargs["max_turns"] == 7


def test_set_goal_keeps_explicit_turn_limit(db: MagicMock) -> None:
    GoalTool()._set_goal("project-1", "ship it", 3, chat_id="chat-1")

    assert db.create_goal.call_args.kwargs["max_turns"] == 3
