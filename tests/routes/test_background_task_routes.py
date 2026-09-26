import json
from types import SimpleNamespace

from starlette.responses import JSONResponse

from suzent.core.background_commands import BackgroundCommands
from suzent.routes import background_task_routes as routes


async def test_list_combines_types_filters_chat_and_pins_running(monkeypatch):
    registry = BackgroundCommands()
    registry.register("chat", "abc", "Build", "host")
    registry.register("other", "def", "Other build", "host")
    monkeypatch.setattr(routes, "get_background_commands", lambda: registry)

    async def subagents(request):
        return JSONResponse(
            {"tasks": [{"task_id": "sub_1", "status": "completed"}], "has_more": False}
        )

    monkeypatch.setattr(routes, "list_subagents", subagents)
    response = await routes.list_background_tasks(
        SimpleNamespace(query_params={"parent_chat_id": "chat"})
    )
    data = json.loads(response.body)
    assert [task["kind"] for task in data["tasks"]] == ["shell", "subagent"]
    assert len(data["tasks"]) == 2


async def test_get_shell_and_missing_task(monkeypatch):
    registry = BackgroundCommands()
    registry.register("chat", "abc", "Build", "host")
    monkeypatch.setattr(routes, "get_background_commands", lambda: registry)
    response = await routes.get_background_task(
        SimpleNamespace(path_params={"task_id": "shell_abc"})
    )
    assert json.loads(response.body)["task"]["kind"] == "shell"
    response = await routes.get_background_task(
        SimpleNamespace(path_params={"task_id": "shell_missing"})
    )
    assert response.status_code == 404


async def test_stream_snapshot_includes_finished_commands_on_reconnect(monkeypatch):
    registry = BackgroundCommands()
    registry.register("chat", "abc", "Build", "host")
    registry.observe("chat", "abc", {"done": True, "exit_code": 0})
    monkeypatch.setattr(routes, "get_background_commands", lambda: registry)
    monkeypatch.setattr(routes, "list_all_tasks", list)
    response = await routes.stream_background_tasks(SimpleNamespace())
    stream = response.body_iterator
    snapshot = await anext(stream)
    assert (
        json.loads(snapshot.removeprefix("data: "))["tasks"][0]["status"] == "completed"
    )
    await stream.aclose()
