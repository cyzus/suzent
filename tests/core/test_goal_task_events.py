"""Regression tests for goal/task event-bus refresh notifications."""


def test_goal_mutations_emit_refresh_events(temp_db, monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", events.append)

    project_id = temp_db.create_project("Live Goals", "live-goals")
    chat_id = temp_db.create_chat("Chat", {}, project_id=project_id)

    goal = temp_db.create_goal(project_id, "Ship it", chat_id=chat_id)
    temp_db.update_goal(goal.id, status="paused")
    temp_db.clear_goal(project_id, chat_id=chat_id)

    assert [event["action"] for event in events] == ["created", "updated", "cleared"]
    assert all(event["event"] == "goal_tasks_changed" for event in events)
    assert all(event["entity"] == "goal" for event in events)
    assert all(event["project_id"] == project_id for event in events)
    assert all(event["chat_id"] == chat_id for event in events)
    assert all(event["goal_id"] == goal.id for event in events)


def test_task_mutations_emit_refresh_events(temp_db, monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", events.append)

    project_id = temp_db.create_project("Live Tasks", "live-tasks")
    chat_id = temp_db.create_chat("Chat", {}, project_id=project_id)

    task = temp_db.create_task(project_id, "Wire updates", "", chat_id=chat_id)
    temp_db.update_task(task.id, status="in_progress")
    temp_db.delete_task(task.id)

    assert [event["action"] for event in events] == ["created", "updated", "deleted"]
    assert all(event["event"] == "goal_tasks_changed" for event in events)
    assert all(event["entity"] == "task" for event in events)
    assert all(event["project_id"] == project_id for event in events)
    assert all(event["chat_id"] == chat_id for event in events)
    assert all(event["task_id"] == task.id for event in events)
