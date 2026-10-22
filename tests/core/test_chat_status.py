import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.core import chat_status, focal_agent
from suzent.core.chat_status import (
    chat_state,
    judge_turn,
    list_chat_states,
    reopen_on_turn_start,
    set_resolved,
)
from suzent.database import ChatDatabase
from suzent.database.models import ChatModel
from suzent.routes.chat_routes import get_chat_states, set_chat_resolved


@pytest.fixture
def db(temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch) -> ChatDatabase:
    for module in (chat_status, focal_agent):
        monkeypatch.setattr(module, "get_database", lambda: temp_db)
    monkeypatch.setattr(focal_agent, "running_chat_ids", lambda: set())
    monkeypatch.setattr(chat_status, "_pending_question_chats", lambda: set())
    return temp_db


@pytest.fixture
def project(db: ChatDatabase) -> str:
    return db.create_project("Website", "website")


def _states(project_id: str) -> dict[str, dict]:
    return {row["title"]: row for row in list_chat_states(project_id)}


def test_a_held_question_or_approval_beats_running_and_resolving() -> None:
    resolved = SimpleNamespace(resolved_at=datetime.now(timezone.utc))
    assert chat_state(
        running=True,
        holds_question=True,
        holds_approval=False,
        blocked_task=None,
        status=resolved,
    ) == ("waiting", "question", None)
    assert chat_state(
        running=True,
        holds_question=False,
        holds_approval=True,
        blocked_task=None,
        status=None,
    ) == ("waiting", "approval", None)
    assert chat_state(
        running=True,
        holds_question=False,
        holds_approval=False,
        blocked_task=None,
        status=resolved,
    ) == ("running", None, None)


def test_resolving_outranks_waits_read_from_tasks_and_replies() -> None:
    task = SimpleNamespace(waiting_reason="Pick a palette")
    judged = SimpleNamespace(
        resolved_at=None, waiting_on_user=True, waiting_reason="Wants a go-ahead"
    )
    kwargs = dict(running=False, holds_question=False, holds_approval=False)

    assert chat_state(**kwargs, blocked_task=task, status=judged) == (
        "waiting",
        "task",
        "Pick a palette",
    )
    assert chat_state(**kwargs, blocked_task=None, status=judged) == (
        "waiting",
        "reply",
        "Wants a go-ahead",
    )
    resolved = SimpleNamespace(
        resolved_at=datetime.now(timezone.utc), waiting_on_user=True
    )
    assert chat_state(**kwargs, blocked_task=task, status=resolved)[0] == "resolved"
    assert chat_state(**kwargs, blocked_task=None, status=None)[0] == "idle"


def test_board_rows_read_tasks_approvals_and_the_judged_reply(db, project) -> None:
    blocked = db.create_chat("Blocked", {}, project_id=project)
    task = db.create_task(project, "Pick", "", chat_id=blocked)
    db.update_task(
        task.id, status="blocked", waiting_kind="user", waiting_reason="Two palettes"
    )
    approval = db.create_chat(
        "Approval", {"_pending_approvals": [{"approvalId": "a"}]}, project_id=project
    )
    asked = db.create_chat("Asked", {}, project_id=project)
    db.update_chat_status(
        asked, waiting_on_user=True, waiting_reason="Go ahead?", summary="Plan ready"
    )
    db.create_chat("Quiet", {}, project_id=project)

    states = _states(project)

    assert states["Blocked"]["state"] == "waiting"
    assert states["Blocked"]["waitingKind"] == "task"
    assert states["Blocked"]["waitingReason"] == "Two palettes"
    assert states["Blocked"]["openTasks"] == 1
    assert states["Approval"]["waitingKind"] == "approval"
    assert states["Asked"]["waitingKind"] == "reply"
    assert states["Asked"]["summary"] == "Plan ready"
    assert states["Quiet"]["state"] == "idle"
    assert approval in {row["chatId"] for row in list_chat_states(project)}


def test_board_leaves_out_regent_sub_agents_and_long_quiet_chats(db, project) -> None:
    focal_agent.get_or_create_focal_chat()
    db.create_chat("Helper", {"platform": "subagent"}, project_id=project)
    old = db.create_chat("Old", {}, project_id=project)
    long_ago = datetime.now(timezone.utc) - timedelta(days=30)
    with db._session() as session:
        chat = session.get(ChatModel, old)
        chat.updated_at = long_ago
        session.add(chat)
        session.commit()

    titles = set(_states(project))

    assert titles == set()


def test_resolving_holds_until_a_new_turn_reopens_the_chat(db, project) -> None:
    chat_id = db.create_chat("Done", {}, project_id=project)
    db.update_chat_status(chat_id, waiting_on_user=True, waiting_reason="Go ahead?")

    assert set_resolved(chat_id, True)
    assert _states(project)["Done"]["state"] == "resolved"
    assert db.get_chat_status(chat_id).waiting_on_user is False

    reopen_on_turn_start(chat_id)

    assert _states(project)["Done"]["state"] == "idle"
    assert set_resolved("missing", True) is False


def _patch_judge(monkeypatch, model, complete):
    class _Router:
        def get_model_id(self, role):
            assert role == "decision"
            return model

    class _Client:
        def __init__(self, model):
            pass

        async def complete(self, **kwargs):
            return await complete(**kwargs)

    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: _Router())
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)


def test_judging_a_turn_records_the_wait_and_a_summary(
    db, project, monkeypatch
) -> None:
    chat_id = db.create_chat("Plan", {}, project_id=project)
    set_resolved(chat_id, True)

    async def answer(**kwargs):
        assert "Which palette?" in kwargs["prompt"]
        return '{"waiting_on_user": true, "reason": "Pick a palette", "summary": "Two palettes ready"}'

    _patch_judge(monkeypatch, "cheap/model", answer)
    asyncio.run(judge_turn(chat_id, "Draft palettes", "Which palette?"))

    row = db.get_chat_status(chat_id)
    assert row.waiting_on_user is True
    assert row.waiting_reason == "Pick a palette"
    assert row.summary == "Two palettes ready"
    assert row.resolved_at is None


def test_a_failed_or_unreadable_judgement_keeps_the_last_record(
    db, project, monkeypatch
) -> None:
    chat_id = db.create_chat("Plan", {}, project_id=project)
    db.update_chat_status(chat_id, summary="Earlier")

    async def garbled(**kwargs):
        return "not json"

    _patch_judge(monkeypatch, "cheap/model", garbled)
    asyncio.run(judge_turn(chat_id, "hi", "reply"))
    assert db.get_chat_status(chat_id).summary == "Earlier"

    async def never(**kwargs):
        raise AssertionError("no model, no call")

    _patch_judge(monkeypatch, None, never)
    asyncio.run(judge_turn(chat_id, "hi", "reply"))
    assert db.get_chat_status(chat_id).summary == "Earlier"


def test_routes_list_states_and_resolve_chats(db, project) -> None:
    chat_id = db.create_chat("Plan", {}, project_id=project)
    app = Starlette(
        routes=[
            Route("/focal/chats", get_chat_states, methods=["GET"]),
            Route("/chats/{chat_id}/resolved", set_chat_resolved, methods=["POST"]),
        ]
    )
    client = TestClient(app)

    assert client.post(f"/chats/{chat_id}/resolved", json={}).status_code == 400
    assert (
        client.post("/chats/missing/resolved", json={"resolved": True}).status_code
        == 404
    )
    assert (
        client.post(f"/chats/{chat_id}/resolved", json={"resolved": True}).status_code
        == 200
    )

    body = client.get("/focal/chats", params={"project_id": project}).json()
    assert body["counts"]["resolved"] == 1
    assert body["chats"][0]["chatId"] == chat_id
