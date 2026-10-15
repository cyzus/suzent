from types import SimpleNamespace

from sqlalchemy import inspect, text

from suzent.routes.goal_task_routes import _task_to_dict
from suzent.tools.tasks.task_update_tool import TaskUpdateTool


def test_waiting_and_result_metadata_survive_reload(temp_db) -> None:
    project_id = temp_db.create_project("Tasks", "task-progress")
    task = temp_db.create_task(project_id, "Report", "Research")
    temp_db.update_task(
        task.id,
        status="blocked",
        waiting_kind="user",
        waiting_reason="Need the source file",
        next_action="Upload the file",
    )
    waiting = _task_to_dict(temp_db.get_task(task.id))
    assert waiting["status"] == "blocked"
    assert waiting["waitingKind"] == "user"
    assert waiting["nextAction"] == "Upload the file"

    temp_db.update_task(task.id, status="in_progress", active_form="Reading sources")
    assert temp_db.get_task(task.id).waiting_reason is None
    temp_db.update_task(
        task.id,
        status="completed",
        result_summary="Report ready",
        result_path="/workspace/report.md",
    )
    result = _task_to_dict(temp_db.get_task(task.id))
    assert result["resultSummary"] == "Report ready"
    assert result["resultPath"] == "/workspace/report.md"
    assert result["completedAt"] is not None


def test_finishing_dependency_unblocks_pending_tasks(temp_db) -> None:
    project_id = temp_db.create_project("Dependencies", "task-dependencies")
    first = temp_db.create_task(project_id, "Collect sources", "")
    second = temp_db.create_task(project_id, "Write report", "", blocked_by=[first.id])
    assert _task_to_dict(second)["status"] == "blocked"
    temp_db.update_task(first.id, status="completed")
    assert _task_to_dict(temp_db.get_task(second.id))["status"] == "pending"


def test_cancelled_tasks_hidden_by_default(temp_db) -> None:
    project_id = temp_db.create_project("Cancelled", "task-cancelled")
    task = temp_db.create_task(project_id, "Abandoned", "")
    temp_db.update_task(task.id, status="cancelled")
    assert temp_db.list_tasks(project_id) == []
    assert len(temp_db.list_tasks(project_id, include_cancelled=True)) == 1


def test_agent_claims_unlinked_task_and_records_wait(temp_db, monkeypatch) -> None:
    project_id = temp_db.create_project("Claim", "task-claim")
    chat_id = temp_db.create_chat("Execute", {}, project_id=project_id)
    task = temp_db.create_task(project_id, "Existing task", "")
    monkeypatch.setattr(
        "suzent.tools.tasks.task_update_tool.get_database", lambda: temp_db
    )
    monkeypatch.setattr(
        "suzent.tools.tasks.task_update_tool.resolve_project_id", lambda _: project_id
    )
    ctx = SimpleNamespace(deps=SimpleNamespace(chat_id=chat_id))
    TaskUpdateTool().forward(
        ctx,
        task.id,
        status="blocked",
        waiting_kind="user",
        waiting_reason="Need confirmation",
        next_action="Confirm the scope",
    )
    updated = temp_db.get_task(task.id)
    assert updated.chat_id == chat_id
    assert updated.waiting_kind == "user"
    assert updated.next_action == "Confirm the scope"


def test_existing_task_table_migrates_without_losing_tasks(temp_db) -> None:
    project_id = temp_db.create_project("Migration", "task-migration")
    task = temp_db.create_task(project_id, "Keep this task", "")
    columns = (
        "waiting_kind",
        "waiting_reason",
        "next_action",
        "result_summary",
        "result_path",
    )
    with temp_db.engine.begin() as connection:
        for column in columns:
            connection.execute(text(f"ALTER TABLE tasks DROP COLUMN {column}"))
    temp_db._run_migrations()
    temp_db._run_migrations()
    migrated = {
        column["name"] for column in inspect(temp_db.engine).get_columns("tasks")
    }
    assert set(columns) <= migrated
    assert temp_db.get_task(task.id).title == "Keep this task"
