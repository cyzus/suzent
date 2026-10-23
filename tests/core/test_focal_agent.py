import time
from inspect import signature
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.core import chat_status, focal_agent
from suzent.core.focal_agent import FOCAL_CHAT_ID, get_or_create_focal_chat
from suzent.database import ChatDatabase
from suzent.tools.agents import agent_lifecycle_tools
from suzent.tools.agents.agent_lifecycle_tools import (
    AgentListTool,
    AgentSendTool,
    _accessible_agent,
)
from suzent.tools.focal import dispatch
from suzent.tools.focal.dispatch import FocalDispatchTool
from suzent.tools.base import ToolErrorCode
from suzent.tools.tasks import task_update_tool
from suzent.tools.tasks.task_update_tool import TaskUpdateTool


@pytest.fixture
def db(temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch) -> ChatDatabase:
    for module in (
        chat_status,
        focal_agent,
        agent_lifecycle_tools,
        dispatch,
        task_update_tool,
    ):
        monkeypatch.setattr(module, "get_database", lambda: temp_db)
    monkeypatch.setattr(focal_agent, "running_chat_ids", lambda: set())
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


def test_focal_chat_is_a_singleton_hidden_from_project_lists(db) -> None:
    first = get_or_create_focal_chat()
    second = get_or_create_focal_chat()

    assert first.id == second.id == FOCAL_CHAT_ID
    assert first.title == "Regent"
    assert first.config["is_focal_agent"] is True
    assert first.config["platform"] == "focal"
    assert FOCAL_CHAT_ID not in {chat.id for chat in db.list_chats(limit=None)}
    assert db.get_chat_count() == 0


def test_global_context_lists_projects_sessions_and_blockers(db) -> None:
    project_id = db.create_project("Website", "website")
    chat_id = db.create_chat("Redesign", {}, project_id=project_id)
    task = db.create_task(project_id, "Pick a palette", "", chat_id=chat_id)
    db.update_task(
        task.id,
        status="blocked",
        waiting_kind="user",
        waiting_reason="Two palettes fit",
        next_action="Choose one",
    )

    context = focal_agent.build_focal_global_context()

    assert context.startswith("# Regent Global Context")
    assert f"slug `website` · id `{project_id}`" in context
    assert f"Session `{chat_id}` · Redesign · idle" in context
    assert f"#{task.id} [blocked] Pick a palette" in context
    assert "waiting on user: Two palettes fit (next: Choose one)" in context


def test_focal_agent_reaches_sessions_in_every_project(db) -> None:
    get_or_create_focal_chat()
    home_chat = db.create_chat("Home chat", {})
    other_project = db.create_project("Other", "other")
    other_chat = db.create_chat("Other chat", {}, project_id=other_project)

    assert _accessible_agent(other_chat, FOCAL_CHAT_ID).id == other_chat
    assert _accessible_agent(other_chat, home_chat) is None


@pytest.mark.asyncio
async def test_any_session_can_message_focal_but_not_read_or_stop_it(
    db, enqueued
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Ops", "ops")
    chat_id = db.create_chat("Deploy", {}, project_id=project_id)

    result = await AgentSendTool().forward(_ctx(chat_id), FOCAL_CHAT_ID, "Shipped")

    assert result.success, result.message
    assert enqueued[0]["target_chat_id"] == FOCAL_CHAT_ID
    assert _accessible_agent(FOCAL_CHAT_ID, chat_id) is None


def test_focal_agent_lists_recent_sessions_across_projects(db, monkeypatch) -> None:
    monkeypatch.setattr(agent_lifecycle_tools, "_agent_is_active", lambda _: False)
    monkeypatch.setattr(
        agent_lifecycle_tools,
        "get_peer_agent_transport",
        lambda: SimpleNamespace(list_agents=lambda: []),
    )
    monkeypatch.setattr(agent_lifecycle_tools.agent_bridge, "list_agents", lambda: [])
    get_or_create_focal_chat()
    project_id = db.create_project("Docs", "docs")
    chat_id = db.create_chat("Write guide", {}, project_id=project_id)
    db.create_task(project_id, "Draft", "", chat_id=chat_id, status="in_progress")

    result = AgentListTool().forward(_ctx(FOCAL_CHAT_ID), status="recent")

    record = next(r for r in result.metadata["agents"] if r["agent_id"] == chat_id)
    assert record["project_slug"] == "docs"
    assert record["tasks"][0]["status"] == "in_progress"
    assert "[docs]" in result.message


@pytest.mark.asyncio
async def test_focal_agent_starts_auto_primary_session_with_task(db, enqueued) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Research", "research")

    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID),
        "new",
        "Survey vector databases",
        project_id="research",
        title="Vector DB survey",
        task_title="Compare vector DBs",
    )

    assert result.success, result.message
    new_chat = db.get_chat(result.metadata["agent_id"])
    assert new_chat.project_id == project_id
    assert new_chat.title == "Vector DB survey"
    assert new_chat.config["permission_mode"] == "auto"
    assert new_chat.config["parent_chat_id"] == FOCAL_CHAT_ID
    task = db.get_task(result.metadata["task_id"])
    assert (task.chat_id, task.status) == (new_chat.id, "in_progress")
    assert enqueued == [
        {
            "sender_chat_id": FOCAL_CHAT_ID,
            "target_chat_id": new_chat.id,
            "content": "Survey vector databases",
        }
    ]


@pytest.mark.asyncio
async def test_only_focal_agent_can_dispatch(db, enqueued) -> None:
    chat_id = db.create_chat("Regular", {})
    db.create_project("Research", "research")

    result = await FocalDispatchTool().forward(
        _ctx(chat_id), "new", "Go", project_id="research"
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.PERMISSION_DENIED
    assert enqueued == []


def test_blocking_on_user_notifies_focal_agent_once(db, enqueued, monkeypatch) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Ops", "ops")
    chat_id = db.create_chat("Deploy", {}, project_id=project_id)
    task = db.create_task(project_id, "Ship release", "")
    monkeypatch.setattr(task_update_tool, "resolve_project_id", lambda _: project_id)

    def block(reason: str) -> None:
        TaskUpdateTool().forward(
            _ctx(chat_id),
            task.id,
            status="blocked",
            waiting_kind="user",
            waiting_reason=reason,
            next_action="Approve the deploy",
        )

    block("Needs production approval")
    block("Needs production approval")

    assert db.get_task(task.id).chat_id == chat_id
    assert len(enqueued) == 1
    notice = enqueued[0]
    assert notice["target_chat_id"] == FOCAL_CHAT_ID
    assert notice["sender_chat_id"] == chat_id
    assert notice["kind"] == "task_blocked_notification"
    assert "Ops" in notice["content"]
    assert "Needs production approval" in notice["content"]

    block("Approval window moved")
    assert len(enqueued) == 2


def test_dependency_wait_does_not_notify_focal_agent(db, enqueued, monkeypatch) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Ops", "ops")
    chat_id = db.create_chat("Deploy", {}, project_id=project_id)
    task = db.create_task(project_id, "Ship release", "", chat_id=chat_id)
    monkeypatch.setattr(task_update_tool, "resolve_project_id", lambda _: project_id)

    TaskUpdateTool().forward(
        _ctx(chat_id), task.id, status="blocked", waiting_kind="dependency"
    )

    assert enqueued == []


def test_kanban_spans_all_projects_with_session_metadata(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import goal_task_routes

    monkeypatch.setattr(goal_task_routes, "get_database", lambda: db)
    client = TestClient(
        Starlette(
            routes=[Route("/project/kanban", goal_task_routes.get_project_kanban)]
        )
    )
    first = db.create_project("Alpha", "alpha")
    second = db.create_project("Beta", "beta")
    chat_id = db.create_chat("Alpha work", {}, project_id=first)
    db.create_task(first, "Alpha task", "", chat_id=chat_id)
    db.create_task(second, "Beta task", "")
    archived = db.create_project("Gone", "gone")
    db.create_task(archived, "Hidden task", "")
    db.update_project(archived, archived=True)

    tasks = client.get("/project/kanban?project_id=__all__").json()["tasks"]

    by_title = {task["title"]: task for task in tasks}
    assert set(by_title) == {"Alpha task", "Beta task"}
    assert by_title["Alpha task"]["chatTitle"] == "Alpha work"
    assert by_title["Alpha task"]["projectSlug"] == "alpha"
    assert by_title["Alpha task"]["chatRunning"] is False
    assert by_title["Beta task"]["projectName"] == "Beta"
    assert by_title["Beta task"]["chatTitle"] is None


def test_kanban_counts_a_foreground_run_as_running(
    db, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes import goal_task_routes

    monkeypatch.setattr(goal_task_routes, "get_database", lambda: db)
    project = db.create_project("Alpha", "alpha")
    chat_id = db.create_chat("Alpha work", {}, project_id=project)
    db.create_task(project, "Alpha task", "", chat_id=chat_id)
    monkeypatch.setattr(focal_agent, "running_chat_ids", lambda: {chat_id})

    tasks = goal_task_routes._all_projects_kanban()["tasks"]

    assert tasks[0]["chatRunning"] is True


def test_a_finished_check_in_on_another_chat_leaves_focal_alone(db, sandbox) -> None:
    get_or_create_focal_chat()

    focal_agent.record_focal_heartbeat_done("some-other-chat")

    assert "focal_heartbeat_signature" not in db.get_chat(FOCAL_CHAT_ID).config


@pytest.mark.parametrize("mode", ["default", "auto", "full_access"])
def test_focal_turn_is_pinned_to_orchestration_tools(db, mode: str) -> None:
    from suzent.core.focal_agent import FOCAL_TOOL_NAMES, apply_focal_tool_policy

    get_or_create_focal_chat()
    config = {
        "permission_mode": mode,
        "tools": ["WriteFileTool", "RunCommandTool", "AgentTool"],
        "denied_tools": ["FocalDispatchTool"],
        "cwd": "/Users/someone/project",
        "sandbox_volumes": ["/Users/someone/data:/mnt/data"],
    }

    apply_focal_tool_policy(config, FOCAL_CHAT_ID)

    assert config["permission_mode"] == "full_access"
    assert config["tools"] == list(FOCAL_TOOL_NAMES)
    assert "FocalDispatchTool" in config["tools"]
    assert "FocalDispatchTool" not in config["denied_tools"]
    assert "AgentSendTool" in config["denied_tools"]
    for tool in ("WriteFileTool", "EditFileTool", "RunCommandTool", "AgentTool"):
        assert tool in config["denied_tools"]
    assert not set(config["tools"]) & set(config["denied_tools"])
    assert config["mcp_disabled"] is True
    assert "cwd" not in config
    assert "sandbox_volumes" not in config


def test_regular_turns_keep_their_tool_choices(db) -> None:
    from suzent.core.focal_agent import apply_focal_tool_policy

    chat_id = db.create_chat("Regular", {})
    config = {"tools": ["WriteFileTool"], "cwd": "/tmp/work"}

    apply_focal_tool_policy(config, chat_id)

    assert config == {"tools": ["WriteFileTool"], "cwd": "/tmp/work"}


def test_disabled_mcp_builds_no_servers() -> None:
    from suzent.agent_manager import _build_mcp_servers

    assert _build_mcp_servers({"mcp_disabled": True}) == []


def test_focal_chat_never_inherits_a_working_directory(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    folder = tmp_path / "granted"
    folder.mkdir()
    chat_id = temp_db.create_chat(
        "SUZENT", {"is_focal_agent": True, "platform": "focal"}
    )
    temp_db.update_chat(chat_id, working_directory=str(folder))

    from suzent.core.context_injection import build_agent_deps

    deps = build_agent_deps(
        chat_id=chat_id,
        user_id="user-1",
        config={
            "sandbox_enabled": False,
            "workspace_root": str(tmp_path / "workspace"),
            "sandbox_data_path": str(tmp_path / "sandbox"),
            "memory_enabled": False,
            "cwd": str(folder),
        },
    )

    assert deps.cwd is None


@pytest.fixture
def sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from suzent.config import CONFIG

    monkeypatch.setattr(CONFIG, "sandbox_data_path", str(tmp_path / "sandbox"))
    return tmp_path / "sandbox"


def test_focal_chat_lives_in_a_hidden_system_project(db, sandbox) -> None:
    chat = get_or_create_focal_chat()

    project = db.get_project(chat.project_id)
    assert project.slug == db.FOCAL_PROJECT_SLUG
    assert project.id not in {p.id for p in db.list_projects()}
    assert project.id in {p.id for p in db.list_projects(include_hidden=True)}
    ok, _ = db.delete_project(project.id)
    assert not ok


def test_existing_focal_chat_moves_out_of_home(db, sandbox) -> None:
    db.create_chat(
        "SUZENT", {"is_focal_agent": True, "platform": "focal"}, chat_id=FOCAL_CHAT_ID
    )
    assert db.get_chat_project_slug(FOCAL_CHAT_ID) == "default"

    get_or_create_focal_chat()

    assert db.get_chat_project_slug(FOCAL_CHAT_ID) == db.FOCAL_PROJECT_SLUG
    assert db.get_chat(FOCAL_CHAT_ID).title == "Regent"


def test_heartbeat_starts_on_once_with_an_editable_checklist(db, sandbox) -> None:
    chat = get_or_create_focal_chat()

    assert chat.config["heartbeat_enabled"] is True
    checklist = sandbox / "projects" / db.FOCAL_PROJECT_SLUG / "heartbeat.md"
    assert checklist.read_text() == focal_agent.DEFAULT_FOCAL_HEARTBEAT

    db.merge_chat_config(FOCAL_CHAT_ID, {"heartbeat_enabled": False})
    checklist.write_text("# mine\n- check the release\n")
    get_or_create_focal_chat()

    assert db.get_chat(FOCAL_CHAT_ID).config["heartbeat_enabled"] is False
    assert checklist.read_text() == "# mine\n- check the release\n"


def test_quiet_heartbeat_skips_the_model_until_something_changes(
    db, sandbox, monkeypatch
) -> None:
    from datetime import timedelta

    get_or_create_focal_chat()
    default = focal_agent.DEFAULT_FOCAL_HEARTBEAT
    project_id = db.create_project("Ops", "ops")
    chat_id = db.create_chat("Deploy", {}, project_id=project_id)
    db.create_task(project_id, "Ship release", "", chat_id=chat_id)

    assert focal_agent.should_run_focal_heartbeat(default) is False

    monkeypatch.setattr(focal_agent, "STALL_AFTER", timedelta(0))
    assert focal_agent.should_run_focal_heartbeat(default) is True
    # Not yet raised: the check-in may never have been claimed, or it failed.
    assert focal_agent.should_run_focal_heartbeat(default) is True

    focal_agent.record_focal_heartbeat_done(FOCAL_CHAT_ID)
    assert focal_agent.should_run_focal_heartbeat(default) is False

    assert focal_agent.should_run_focal_heartbeat("# mine\n- check email\n") is True


def test_skipped_heartbeat_counts_as_a_run(db, sandbox) -> None:
    get_or_create_focal_chat()

    focal_agent.record_skipped_heartbeat()

    assert db.get_chat(FOCAL_CHAT_ID).config["heartbeat_last_run_at"]


@pytest.fixture
def schedule_db(db, monkeypatch):
    from suzent.tools import schedule_tool

    monkeypatch.setattr(schedule_tool, "get_database", lambda: db)
    return db


@pytest.mark.parametrize(
    ("kind", "quiet", "delivery"),
    [("reminder", False, "announce"), ("check", True, "none")],
)
def test_focal_wakeups_run_in_focal_and_reminders_always_notify(
    schedule_db, sandbox, kind, quiet, delivery
) -> None:
    from suzent.tools.focal.schedule import FocalScheduleTool

    get_or_create_focal_chat()

    result = FocalScheduleTool().forward(
        _ctx(FOCAL_CHAT_ID),
        action="create",
        kind=kind,
        prompt="Tell the user the release window opens",
        in_minutes=30,
    )

    assert result.success, result.message
    job = schedule_db.get_cron_job(result.metadata["task_id"])
    assert job.chat_id == FOCAL_CHAT_ID
    assert job.context_mode == "bound"
    assert bool(job.suppress_ok) is quiet
    assert job.delivery_mode == delivery


def test_focal_wakeups_refuse_other_chats_and_stay_out_of_reach(
    schedule_db, sandbox
) -> None:
    from suzent.tools.registry import get_tool_capabilities
    from suzent.tools.focal.schedule import FocalScheduleTool

    chat_id = schedule_db.create_chat("Regular", {})

    result = FocalScheduleTool().forward(
        _ctx(chat_id), action="create", prompt="x", in_minutes=5
    )

    assert result.error_code == ToolErrorCode.PERMISSION_DENIED
    assert FocalScheduleTool.deferrable is False
    assert "FocalScheduleTool" not in {
        tool["id"]
        for capability in get_tool_capabilities()
        for tool in capability["tools"]
    }
    assert "FocalScheduleTool" in focal_agent.FOCAL_TOOL_NAMES
    assert "ScheduleTool" not in focal_agent.FOCAL_TOOL_NAMES


def test_focal_hears_when_a_session_it_started_finishes(
    db, sandbox, enqueued, monkeypatch
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Docs", "docs")
    chat_id = db.create_chat(
        "Guide", {"parent_chat_id": FOCAL_CHAT_ID}, project_id=project_id
    )
    first = db.create_task(project_id, "Draft", "", chat_id=chat_id)
    second = db.create_task(project_id, "Review", "", chat_id=chat_id)
    monkeypatch.setattr(task_update_tool, "resolve_project_id", lambda _: project_id)

    TaskUpdateTool().forward(_ctx(chat_id), first.id, status="completed")
    assert enqueued == []

    TaskUpdateTool().forward(
        _ctx(chat_id), second.id, status="completed", result_summary="Approved"
    )

    assert len(enqueued) == 1
    notice = enqueued[0]
    assert notice["target_chat_id"] == FOCAL_CHAT_ID
    assert notice["kind"] == "session_finished_notification"
    assert "Approved" in notice["content"]


def test_sessions_focal_did_not_start_finish_quietly(
    db, sandbox, enqueued, monkeypatch
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Docs", "docs")
    chat_id = db.create_chat("Guide", {}, project_id=project_id)
    task = db.create_task(project_id, "Draft", "", chat_id=chat_id)
    monkeypatch.setattr(task_update_tool, "resolve_project_id", lambda _: project_id)

    TaskUpdateTool().forward(_ctx(chat_id), task.id, status="completed")

    assert enqueued == []


def test_focal_replies_to_events_become_notifications(db, sandbox) -> None:
    focal_agent.announce_focal_reply(FOCAL_CHAT_ID, "Deploy needs your approval.")
    focal_agent.announce_focal_reply(FOCAL_CHAT_ID, "   ")
    focal_agent.announce_focal_reply("some-other-chat", "Hello")

    notices = db.drain_background_notifications()
    assert [(n.source, n.result) for n in notices] == [
        ("focal", "Deploy needs your approval.")
    ]


def test_heartbeat_runner_skips_a_quiet_focal_check_in(
    db, sandbox, monkeypatch
) -> None:
    from suzent.core import heartbeat

    monkeypatch.setattr(heartbeat, "get_database", lambda: db)
    get_or_create_focal_chat()
    runner = heartbeat.HeartbeatRunner()
    runner._enabled = True

    runner.mark_heartbeat_pending(FOCAL_CHAT_ID)

    assert FOCAL_CHAT_ID not in runner._pending_heartbeats
    assert db.get_chat(FOCAL_CHAT_ID).config["heartbeat_last_run_at"]


def test_focal_panel_lists_fixed_tools_and_own_wakeups(
    schedule_db, sandbox, monkeypatch
) -> None:
    from suzent.routes import chat_routes
    from suzent.tools.focal.schedule import FocalScheduleTool

    monkeypatch.setattr(chat_routes, "get_database", lambda: schedule_db)
    client = TestClient(
        Starlette(
            routes=[
                Route("/focal/panel", chat_routes.get_focal_panel),
                Route(
                    "/focal/wakeups/{job_id:int}",
                    chat_routes.delete_focal_wakeup,
                    methods=["DELETE"],
                ),
            ]
        )
    )
    get_or_create_focal_chat()
    later = FocalScheduleTool().forward(
        _ctx(FOCAL_CHAT_ID), action="create", kind="check", prompt="Look", in_minutes=90
    )
    sooner = FocalScheduleTool().forward(
        _ctx(FOCAL_CHAT_ID),
        action="create",
        kind="reminder",
        name="Stand-up",
        prompt="Remind the user",
        in_minutes=10,
    )
    other_chat = schedule_db.create_chat("Regular", {})
    foreign = schedule_db.create_cron_job(
        name="theirs", prompt="x", cron_expr="0 9 * * *", chat_id=other_chat
    )

    panel = client.get("/focal/panel").json()

    assert [tool["id"] for tool in panel["tools"]] == list(focal_agent.FOCAL_TOOL_NAMES)
    assert (
        next(t for t in panel["tools"] if t["id"] == "FocalScheduleTool")["runtimeName"]
        == "schedule_wakeup"
    )
    wakeups = panel["wakeups"]
    assert [w["id"] for w in wakeups] == [
        sooner.metadata["task_id"],
        later.metadata["task_id"],
    ]
    assert wakeups[0]["kind"] == "reminder" and wakeups[0]["name"] == "Stand-up"
    assert wakeups[1]["kind"] == "check"
    assert wakeups[0]["nextRunAt"]

    assert client.delete(f"/focal/wakeups/{foreign}").status_code == 404
    assert client.delete(f"/focal/wakeups/{sooner.metadata['task_id']}").json() == {
        "ok": True
    }
    assert [w["id"] for w in client.get("/focal/panel").json()["wakeups"]] == [
        later.metadata["task_id"]
    ]


def test_auto_title_leaves_suzent_alone(db, sandbox) -> None:
    from suzent.core.auto_title import should_generate_auto_title

    chat = get_or_create_focal_chat()
    regular = db.get_chat(db.create_chat("New Chat", {}))

    assert should_generate_auto_title(chat) is False
    assert should_generate_auto_title(regular) is True


def test_a_renamed_focal_chat_gets_its_name_back(db, sandbox) -> None:
    get_or_create_focal_chat()
    db.update_chat(FOCAL_CHAT_ID, title="可用工具与功能列表")

    assert get_or_create_focal_chat().title == "Regent"


def test_focal_status_reports_new_messages(db, sandbox) -> None:
    get_or_create_focal_chat()
    db.merge_chat_config(
        FOCAL_CHAT_ID,
        {"unread_count": 2, "_summary_last_message": "Deploy needs your approval."},
    )

    status = focal_agent.focal_status()

    assert status["unread"] == 2
    assert status["lastMessage"] == "Deploy needs your approval."


def _focal_message(target: str, *, sender: str = FOCAL_CHAT_ID) -> dict:
    return {
        "message_id": "msg-from-focal",
        "kind": "agent_message",
        "sender_chat_id": sender,
        "target_chat_id": target,
    }


def test_a_sessions_answer_to_focal_goes_back_to_focal(db, sandbox, enqueued) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Mac mini", "mac-mini")
    chat_id = db.create_chat("Servers", {}, project_id=project_id)

    routed = focal_agent.route_focal_reply(
        _focal_message(chat_id), "任务 #195 已完成，向您汇报：Caddy 域名已生效。"
    )

    assert routed is True
    notice = enqueued[0]
    assert notice["target_chat_id"] == FOCAL_CHAT_ID
    assert notice["sender_chat_id"] == chat_id
    assert notice["kind"] == "session_reply_notification"
    assert notice["message_id"] == "focal-reply-msg-from-focal"
    assert "Servers" in notice["content"] and "Mac mini" in notice["content"]
    assert "任务 #195 已完成" in notice["content"]


def test_only_answers_to_focal_are_routed_to_it(db, sandbox, enqueued) -> None:
    get_or_create_focal_chat()
    chat_id = db.create_chat("Servers", {})
    other = db.create_chat("Other", {})

    assert (
        focal_agent.route_focal_reply(_focal_message(chat_id, sender=other), "Done")
        is False
    )
    assert focal_agent.route_focal_reply(_focal_message(chat_id), "   ") is False
    assert focal_agent.route_focal_reply(_focal_message(FOCAL_CHAT_ID), "Hi") is False
    assert enqueued == []


def test_long_answers_are_trimmed_for_focal(db, sandbox, enqueued) -> None:
    get_or_create_focal_chat()
    chat_id = db.create_chat("Servers", {})

    focal_agent.route_focal_reply(_focal_message(chat_id), "x" * 10_000)

    assert len(enqueued[0]["content"]) < 4_200
    assert "agent_read" in enqueued[0]["content"]


def _request_from_focal(db, chat_id: str) -> dict:
    record, _ = db.enqueue_agent_message(
        message_id="msg-request",
        target_chat_id=chat_id,
        content="Upgrade Caddy",
        sender_chat_id=FOCAL_CHAT_ID,
    )
    return record


def test_a_session_that_already_reported_is_not_routed_again(db, sandbox, enqueued):
    get_or_create_focal_chat()
    chat_id = db.create_chat("Servers", {})
    request = _request_from_focal(db, chat_id)
    db.enqueue_agent_message(
        message_id="msg-report",
        target_chat_id=FOCAL_CHAT_ID,
        content="Caddy is upgraded.",
        sender_chat_id=chat_id,
    )

    routed = focal_agent.route_focal_reply(
        {**_focal_message(chat_id), "message_id": request["message_id"]},
        "Caddy is upgraded.",
    )

    assert routed is False
    assert enqueued == []


def test_a_report_sent_before_the_request_does_not_block_the_reply(
    db, sandbox, enqueued
):
    get_or_create_focal_chat()
    chat_id = db.create_chat("Servers", {})
    db.enqueue_agent_message(
        message_id="msg-old-report",
        target_chat_id=FOCAL_CHAT_ID,
        content="Earlier unrelated report.",
        sender_chat_id=chat_id,
    )
    time.sleep(0.01)
    request = _request_from_focal(db, chat_id)

    routed = focal_agent.route_focal_reply(
        {**_focal_message(chat_id), "message_id": request["message_id"]},
        "Caddy is upgraded.",
    )

    assert routed is True
    assert enqueued[0]["kind"] == "session_reply_notification"


def test_a_session_without_a_report_still_answers_focal(db, sandbox, enqueued):
    get_or_create_focal_chat()
    chat_id = db.create_chat("Servers", {})
    request = _request_from_focal(db, chat_id)

    routed = focal_agent.route_focal_reply(
        {**_focal_message(chat_id), "message_id": request["message_id"]},
        "Caddy is upgraded.",
    )

    assert routed is True
    assert enqueued[0]["message_id"] == "focal-reply-msg-request"


@pytest.mark.asyncio
async def test_sending_work_makes_focal_follow_the_session(
    db, sandbox, enqueued, monkeypatch
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Mac mini", "mac-mini")
    chat_id = db.create_chat("Servers", {}, project_id=project_id)
    task = db.create_task(project_id, "Upgrade Caddy", "", chat_id=chat_id)

    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID), chat_id, "Finish #1"
    )

    assert result.success
    assert "reply will wake you" in result.message
    assert db.get_chat(chat_id).config["focal_watching"] is True

    monkeypatch.setattr(task_update_tool, "resolve_project_id", lambda _: project_id)
    TaskUpdateTool().forward(_ctx(chat_id), task.id, status="completed")
    assert [n["kind"] for n in enqueued[1:]] == ["session_finished_notification"]


def test_no_finished_notice_while_focals_request_is_still_running(
    db, sandbox, enqueued, monkeypatch
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Mac mini", "mac-mini")
    chat_id = db.create_chat("Servers", {"focal_watching": True}, project_id=project_id)
    task = db.create_task(project_id, "Upgrade Caddy", "", chat_id=chat_id)
    db.enqueue_agent_message(
        message_id="in-flight",
        sender_chat_id=FOCAL_CHAT_ID,
        target_chat_id=chat_id,
        content="Finish #1",
    )
    monkeypatch.setattr(task_update_tool, "resolve_project_id", lambda _: project_id)

    TaskUpdateTool().forward(_ctx(chat_id), task.id, status="completed")

    assert enqueued == []


@pytest.mark.asyncio
async def test_focal_asks_with_a_form_but_does_not_wait(db, sandbox) -> None:
    import asyncio

    from suzent.a2ui import pending as pending_questions
    from suzent.tools.ask_question_tool import AskQuestionTool, QuestionItem

    get_or_create_focal_chat()
    queue: asyncio.Queue = asyncio.Queue()
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            chat_id=FOCAL_CHAT_ID,
            a2ui_queue=queue,
            social_context={},
            interaction_profile="interactive",
        )
    )

    result = await asyncio.wait_for(
        AskQuestionTool().forward(
            ctx,
            questions=[QuestionItem(question="用哪个配色？", options=["暖色", "冷色"])],
        ),
        timeout=1,
    )

    assert result.success
    assert result.metadata["waiting"] is False
    event = queue.get_nowait()
    assert event["target"] == "inline"
    assert not event.get("deferred")
    assert event["component"]["action"] == "submit_question"
    assert [field["name"] for field in event["component"]["fields"]] == ["用哪个配色？"]
    assert pending_questions.resolve(FOCAL_CHAT_ID, event["id"], {}) is False


@pytest.mark.asyncio
async def test_focal_never_waits_on_a_session(
    db, sandbox, enqueued, monkeypatch
) -> None:
    get_or_create_focal_chat()
    chat_id = db.create_chat("Servers", {})

    async def must_not_wait(*args, **kwargs):
        raise AssertionError("Regent waited on another agent")

    monkeypatch.setattr(AgentSendTool, "_send_and_wait", staticmethod(must_not_wait))

    assert "wait" not in signature(FocalDispatchTool.forward).parameters
    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID), chat_id, "Finish #1"
    )

    assert result.success
    assert enqueued[0]["target_chat_id"] == chat_id
    assert "reply will wake you" in result.message


@pytest.mark.asyncio
async def test_focal_does_not_block_on_external_agents(
    db, sandbox, monkeypatch
) -> None:
    get_or_create_focal_chat()
    monkeypatch.setattr(
        agent_lifecycle_tools.agent_bridge, "parse_address", lambda agent_id: True
    )

    def must_not_delegate(*args):
        raise AssertionError("Regent blocked on an external agent")

    monkeypatch.setattr(
        agent_lifecycle_tools.agent_bridge, "delegate", must_not_delegate
    )

    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID), "a2a:research-bot", "Summarise"
    )

    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert "project session" in result.message


def test_focal_status_counts_stalled_sessions_like_the_board(db, sandbox) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Ops", "ops")
    idle = db.create_chat("Idle", {}, project_id=project_id)
    blocked = db.create_chat("Blocked", {}, project_id=project_id)
    done = db.create_chat("Done", {}, project_id=project_id)
    db.create_task(project_id, "Ship", "", chat_id=idle)
    db.create_task(project_id, "Also pending", "", chat_id=blocked)
    waiting = db.create_task(project_id, "Pick", "", chat_id=blocked)
    db.update_task(waiting.id, status="blocked", waiting_kind="user")
    finished = db.create_task(project_id, "Old", "", chat_id=done)
    db.update_task(finished.id, status="completed")

    status = focal_agent.focal_status()

    assert status["stalled"] == 1
    assert status["waiting"] == 1
    assert status["waitingByProject"] == {project_id: 1}
    assert status["waitingByChat"] == {blocked: 1}


def test_focal_status_reports_when_suzent_last_spoke(db, sandbox) -> None:
    from datetime import datetime, timezone

    get_or_create_focal_chat()
    assert focal_agent.focal_status()["lastMessageAt"] is None

    db.set_last_result_at(FOCAL_CHAT_ID)

    last = datetime.fromisoformat(focal_agent.focal_status()["lastMessageAt"])
    assert (datetime.now(timezone.utc) - last).total_seconds() < 60


def test_only_suzent_sees_the_dispatch_parameters() -> None:
    from suzent.tools.registry import _tool_description

    send_params = signature(AgentSendTool.forward).parameters
    assert not {"project_id", "title", "task_title"} & set(send_params)
    assert (FocalDispatchTool.group, FocalDispatchTool.deferrable) == ("", False)
    assert FocalDispatchTool.tool_name != AgentSendTool.tool_name
    for tool in (AgentSendTool, FocalDispatchTool):
        described = [_tool_description(tool)] + [
            str(param.annotation)
            for param in signature(tool.forward).parameters.values()
        ]
        assert not any("Focal Agent" in text for text in described)


def test_suzents_tools_speak_to_it_as_suzent() -> None:
    from suzent.core.focal_agent import FOCAL_TOOL_NAMES
    from suzent.tools.registry import _all_tool_classes, _tool_description

    for tool in _all_tool_classes():
        if tool.name not in FOCAL_TOOL_NAMES:
            continue
        described = [_tool_description(tool)] + [
            str(param.annotation)
            for param in signature(tool.forward).parameters.values()
        ]
        for stale in ("agent_send", "Focal Agent"):
            assert not any(stale in text for text in described), (tool.name, stale)


def test_an_untouched_old_checklist_is_upgraded(db, sandbox) -> None:
    get_or_create_focal_chat()
    path = db.get_project_dir(FOCAL_CHAT_ID) / "heartbeat.md"
    path.write_text(focal_agent._PREVIOUS_FOCAL_HEARTBEATS[0], encoding="utf-8")

    get_or_create_focal_chat()

    assert path.read_text(encoding="utf-8") == focal_agent.DEFAULT_FOCAL_HEARTBEAT
    path.write_text("- My own item\n", encoding="utf-8")
    get_or_create_focal_chat()
    assert path.read_text(encoding="utf-8") == "- My own item\n"


@pytest.mark.asyncio
async def test_suzent_keeps_its_own_notes(db, sandbox) -> None:
    from suzent.tools.focal.notes import FocalNotesTool

    get_or_create_focal_chat()
    path = db.get_project_dir(FOCAL_CHAT_ID) / "context.md"
    assert path.read_text(encoding="utf-8") == focal_agent.DEFAULT_FOCAL_NOTES
    path.write_text("", encoding="utf-8")
    tool = FocalNotesTool()

    await tool.forward(_ctx(FOCAL_CHAT_ID), "- Ask before anything about deploys")
    await tool.forward(_ctx(FOCAL_CHAT_ID), "- Reports in Chinese, one line each")
    assert path.read_text(encoding="utf-8") == (
        "- Ask before anything about deploys\n- Reports in Chinese, one line each\n"
    )

    result = await tool.forward(
        _ctx(FOCAL_CHAT_ID), "Reports in English", old_text="Reports in Chinese"
    )
    assert result.success
    assert "Reports in English, one line each" in result.message

    await tool.forward(
        _ctx(FOCAL_CHAT_ID), "", old_text="- Ask before anything about deploys\n"
    )
    assert path.read_text(encoding="utf-8") == "- Reports in English, one line each\n"


@pytest.mark.asyncio
async def test_notes_refuse_ambiguous_edits_other_chats_and_overflow(
    db, sandbox
) -> None:
    from suzent.tools.focal.notes import MAX_NOTES_CHARS, FocalNotesTool

    get_or_create_focal_chat()
    (db.get_project_dir(FOCAL_CHAT_ID) / "context.md").write_text("")
    tool = FocalNotesTool()
    await tool.forward(_ctx(FOCAL_CHAT_ID), "- quiet after 22:00\n- quiet on Sunday")

    ambiguous = await tool.forward(_ctx(FOCAL_CHAT_ID), "x", old_text="quiet")
    other = await tool.forward(_ctx(db.create_chat("Regular", {})), "- rule")
    overflow = await tool.forward(_ctx(FOCAL_CHAT_ID), "x" * MAX_NOTES_CHARS)

    assert ambiguous.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert other.error_code == ToolErrorCode.PERMISSION_DENIED
    assert overflow.error_code == ToolErrorCode.INVALID_ARGUMENT
    notes = (db.get_project_dir(FOCAL_CHAT_ID) / "context.md").read_text()
    assert notes == "- quiet after 22:00\n- quiet on Sunday\n"


def test_notes_tool_is_suzents_alone() -> None:
    from suzent.core.focal_agent import FOCAL_TOOL_NAMES
    from suzent.tools.focal.notes import FocalNotesTool

    assert "FocalNotesTool" in FOCAL_TOOL_NAMES
    assert (FocalNotesTool.group, FocalNotesTool.deferrable) == ("", False)


def test_suzents_memory_section_points_at_its_notes() -> None:
    from suzent.memory.memory_context import format_core_memory_section

    focal = format_core_memory_section({"context": "- rule"}, chat_id=FOCAL_CHAT_ID)
    regular = format_core_memory_section({"context": "- rule"}, chat_id="chat-1")

    assert "update_notes" in focal
    assert "edit_file" not in focal
    assert "edit_file" in regular and "update_notes" not in regular
    assert "<!-- /memory:generated" in regular


@pytest.mark.asyncio
async def test_notes_file_rules_under_their_section(db, sandbox) -> None:
    from suzent.tools.focal.notes import FocalNotesTool

    get_or_create_focal_chat()
    path = db.get_project_dir(FOCAL_CHAT_ID) / "context.md"
    tool = FocalNotesTool()

    await tool.forward(_ctx(FOCAL_CHAT_ID), "- after 22:00", section="Don't disturb")
    await tool.forward(_ctx(FOCAL_CHAT_ID), "- Sundays", section="don't disturb")
    await tool.forward(_ctx(FOCAL_CHAT_ID), "- ask over $50", section="Budget")

    notes = path.read_text(encoding="utf-8")
    assert "## Don't disturb\n- after 22:00\n- Sundays\n\n## Project names" in notes
    assert notes.endswith("\n## Budget\n- ask over $50\n")


def test_edited_notes_are_never_reseeded(db, sandbox) -> None:
    get_or_create_focal_chat()
    path = db.get_project_dir(FOCAL_CHAT_ID) / "context.md"
    path.write_text("- my rule\n", encoding="utf-8")

    get_or_create_focal_chat()

    assert path.read_text(encoding="utf-8") == "- my rule\n"


def test_global_context_shows_each_projects_overview(db, sandbox) -> None:
    db.create_project("Site", "site")
    db.create_project("Ops", "ops")
    db.create_project("Bare", "bare")
    (sandbox / "projects" / "site").mkdir(parents=True)
    (sandbox / "projects" / "site" / "context.md").write_text(
        "# Site\n## Overview\nMarketing site rebuild in Next.js\n## Decisions\n- x\n"
    )
    (sandbox / "projects" / "ops").mkdir(parents=True)
    (sandbox / "projects" / "ops" / "context.md").write_text(
        "# Migration plan\n\nMove every service to the Mac mini. " + "y" * 300
    )

    context = focal_agent.build_focal_global_context()

    assert "slug `site`" in context and "— Marketing site rebuild in Next.js" in context
    ops_line = next(line for line in context.splitlines() if "slug `ops`" in line)
    assert "— Move every service to the Mac mini." in ops_line
    assert ops_line.endswith("…")
    bare_line = next(line for line in context.splitlines() if "slug `bare`" in line)
    assert "—" not in bare_line


@pytest.mark.asyncio
async def test_only_the_suzent_singleton_keeps_notes(db, sandbox) -> None:
    from suzent.tools.focal.notes import FocalNotesTool

    get_or_create_focal_chat()
    lookalike = db.create_chat("Old focal", {"is_focal_agent": True})

    result = await FocalNotesTool().forward(_ctx(lookalike), "- rule")

    assert result.error_code == ToolErrorCode.PERMISSION_DENIED
    notes = (db.get_project_dir(FOCAL_CHAT_ID) / "context.md").read_text()
    assert notes == focal_agent.DEFAULT_FOCAL_NOTES


def test_an_unreadable_project_context_drops_only_its_overview(db, sandbox) -> None:
    db.create_project("Broken", "broken")
    db.create_project("Fine", "fine")
    for slug, content in (("broken", b"\xff\xfe bad"), ("fine", b"All good")):
        (sandbox / "projects" / slug).mkdir(parents=True)
        (sandbox / "projects" / slug / "context.md").write_bytes(content)

    context = focal_agent.build_focal_global_context()

    assert "slug `broken`" in context
    assert "slug `fine` · id" in context and "— All good" in context


@pytest.fixture
def acp_agents(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """ACP agent ids mapped to whether they are installed."""
    from suzent.acp.registry import ACPAgentRegistry

    installed = {"codex": True, "gemini": False}

    def get(self, agent_id: str):
        if agent_id not in installed:
            raise KeyError(agent_id)
        return SimpleNamespace(id=agent_id, available=installed[agent_id])

    monkeypatch.setattr(ACPAgentRegistry, "get", get)
    return installed


@pytest.mark.asyncio
async def test_suzent_starts_an_acp_session_in_ask_mode(
    db, sandbox, enqueued, acp_agents
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Website", "website")

    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID),
        "new",
        "Fix the broken nav link",
        project_id="website",
        title="Nav fix",
        acp_agent_id="codex",
    )

    assert result.success, result.message
    assert "on ACP agent 'codex'" in result.message
    chat = db.get_chat(result.metadata["agent_id"])
    assert chat.project_id == project_id
    assert {
        key: chat.config.get(key)
        for key in ("runtime", "acp_agent_id", "permission_mode", "parent_chat_id")
    } == {
        "runtime": "acp",
        "acp_agent_id": "codex",
        "permission_mode": "default",
        "parent_chat_id": FOCAL_CHAT_ID,
    }
    assert db.list_tasks(project_id=project_id) == []
    assert enqueued[0]["target_chat_id"] == chat.id
    context = focal_agent.build_focal_global_context()
    assert f"Session `{chat.id}` · Nav fix · idle · ACP `codex`" in context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent", "task_title", "code"),
    [
        ("codex", "Fix nav", ToolErrorCode.INVALID_ARGUMENT),
        ("missing", None, ToolErrorCode.NOT_FOUND),
        ("gemini", None, ToolErrorCode.INVALID_ARGUMENT),
    ],
)
async def test_acp_sessions_refuse_tasks_and_unusable_agents(
    db, sandbox, enqueued, acp_agents, agent, task_title, code
) -> None:
    get_or_create_focal_chat()
    project_id = db.create_project("Website", "website")

    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID),
        "new",
        "Fix the broken nav link",
        project_id="website",
        task_title=task_title,
        acp_agent_id=agent,
    )

    assert result.error_code == code
    assert enqueued == []
    assert db.list_chats(project_id=project_id) == []


def test_agent_list_tells_suzent_to_dispatch_acp_agents(db, sandbox) -> None:
    get_or_create_focal_chat()
    regular = db.create_chat("Regular", {})

    for_suzent = AgentListTool().forward(_ctx(FOCAL_CHAT_ID), "acp")
    for_regular = AgentListTool().forward(_ctx(regular), "acp")

    assert "agent_dispatch(agent_id='new'" in for_suzent.message
    assert "agent(runtime='acp'" not in for_suzent.message
    assert "agent(runtime='acp'" in for_regular.message


@pytest.mark.asyncio
async def test_suzent_messages_a_paired_suzent_without_waiting(
    db, sandbox, monkeypatch
) -> None:
    get_or_create_focal_chat()
    sent: list[dict] = []
    transport = SimpleNamespace(
        list_agents=lambda: [],
        peer_id=lambda agent_id: "laptop" if agent_id.startswith("peer:") else None,
        enqueue=lambda **kwargs: (
            sent.append(kwargs) or {"message_id": "msg-peer", "status": "pending"},
            True,
        ),
    )
    monkeypatch.setattr(
        agent_lifecycle_tools, "get_peer_agent_transport", lambda: transport
    )

    result = await FocalDispatchTool().forward(
        _ctx(FOCAL_CHAT_ID), "peer:laptop", "Run the backup on the laptop"
    )

    assert result.success, result.message
    assert result.metadata["transport"] == "suzent_peer"
    assert sent == [
        {
            "agent_id": "peer:laptop",
            "sender_chat_id": FOCAL_CHAT_ID,
            "content": "Run the backup on the laptop",
        }
    ]


@pytest.mark.parametrize("index", [0, 1])
def test_every_old_built_in_checklist_is_upgraded(db, sandbox, index) -> None:
    get_or_create_focal_chat()
    path = db.get_project_dir(FOCAL_CHAT_ID) / "heartbeat.md"
    old = focal_agent._PREVIOUS_FOCAL_HEARTBEATS[index]
    assert old.startswith("# SUZENT check-in")
    path.write_text(old, encoding="utf-8")

    get_or_create_focal_chat()

    assert path.read_text(encoding="utf-8") == focal_agent.DEFAULT_FOCAL_HEARTBEAT
    assert focal_agent.should_run_focal_heartbeat(old) is False


def test_untouched_suzent_notes_become_regents(db, sandbox) -> None:
    get_or_create_focal_chat()
    path = db.get_project_dir(FOCAL_CHAT_ID) / "context.md"
    path.write_text(focal_agent._PREVIOUS_FOCAL_NOTES[0], encoding="utf-8")

    get_or_create_focal_chat()

    assert path.read_text(encoding="utf-8").startswith("# Regent's notes")
