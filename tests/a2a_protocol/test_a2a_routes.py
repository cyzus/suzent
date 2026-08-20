"""
A2A HTTP surface: discovery gating, JSON-RPC envelope handling, and a full
message/send round trip with the agent turn stubbed out.
"""

import json

import pytest
from starlette.testclient import TestClient

from suzent.a2a import tasks as tasks_module
from suzent.a2a.types import TaskState
from suzent.config import CONFIG
from suzent.server import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fresh_task_store(monkeypatch):
    """Each test gets its own store so task ids never leak between them."""
    store = tasks_module.TaskStore()
    monkeypatch.setattr(tasks_module, "_store", store)
    return store


@pytest.fixture
def published(monkeypatch):
    monkeypatch.setattr(CONFIG, "a2a_enabled", True, raising=False)


class _FakeProcessor:
    """Stands in for ChatProcessor, emitting AG-UI frames like the real one."""

    frames: list[str] = []

    def process_turn(self, **_kwargs):
        async def _gen():
            for frame in self.frames:
                yield frame

        return _gen()


def _stub_agent(monkeypatch, frames):
    import suzent.agent_manager as agent_manager
    import suzent.core.chat_processor as chat_processor
    import suzent.database as database

    _FakeProcessor.frames = frames
    monkeypatch.setattr(chat_processor, "ChatProcessor", _FakeProcessor)
    monkeypatch.setattr(
        agent_manager, "build_agent_config", lambda *a, **k: {}, raising=False
    )

    class _FakeDB:
        def ensure_channel_chat(self, *a, **k):
            return True

    monkeypatch.setattr(database, "get_database", lambda: _FakeDB(), raising=False)


def _text_frame(delta: str) -> str:
    return f"data: {json.dumps({'type': 'TEXT_MESSAGE_CONTENT', 'delta': delta})}\n\n"


def _rpc(method: str, params: dict, request_id="r1") -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _message(text: str, **extra) -> dict:
    return {
        "message": {
            "kind": "message",
            "messageId": "m1",
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            **extra,
        }
    }


# ─── Discovery ───────────────────────────────────────────────────────


def test_agent_card_hidden_until_published(monkeypatch):
    monkeypatch.setattr(CONFIG, "a2a_enabled", False, raising=False)
    assert client.get("/.well-known/agent-card.json").status_code == 404


def test_agent_card_is_spec_shaped(published):
    card = client.get("/.well-known/agent-card.json").json()

    assert card["protocolVersion"] == "0.3.0"
    assert card["preferredTransport"] == "JSONRPC"
    assert card["url"].endswith("/a2a/v1")
    assert card["capabilities"]["streaming"] is True
    assert card["securitySchemes"]["deviceGrant"]["scheme"] == "bearer"
    # The OS environment is surfaced so a delegating agent knows where work lands.
    assert card["skills"][0]["id"] == "chat"
    assert card["description"].startswith("Sovereign Suzent agent running on ")


def test_card_name_follows_config(published, monkeypatch):
    monkeypatch.setattr(CONFIG, "a2a_agent_name", "Water-Cooled-Rig", raising=False)
    assert client.get("/.well-known/agent-card.json").json()["name"] == (
        "Water-Cooled-Rig"
    )


# ─── JSON-RPC envelope ───────────────────────────────────────────────


def test_rejects_non_jsonrpc_body():
    response = client.post("/a2a/v1", json={"hello": "world"})
    assert response.json()["error"]["code"] == -32600


def test_unknown_method():
    response = client.post("/a2a/v1", json=_rpc("agents/summon", {}))
    assert response.json()["error"]["code"] == -32601


def test_push_notifications_reported_unsupported():
    response = client.post(
        "/a2a/v1", json=_rpc("tasks/pushNotificationConfig/set", {"id": "x"})
    )
    assert response.json()["error"]["code"] == -32003


def test_message_without_text_is_invalid_params():
    body = _rpc(
        "message/send",
        {
            "message": {
                "kind": "message",
                "messageId": "m1",
                "role": "user",
                "parts": [],
            }
        },
    )
    assert client.post("/a2a/v1", json=body).json()["error"]["code"] == -32602


def test_tasks_get_unknown_task():
    response = client.post("/a2a/v1", json=_rpc("tasks/get", {"id": "nope"}))
    assert response.json()["error"]["code"] == -32001


# ─── Task execution ──────────────────────────────────────────────────


def test_message_send_runs_a_turn_and_completes(monkeypatch):
    _stub_agent(monkeypatch, [_text_frame("Hel"), _text_frame("lo")])

    result = client.post(
        "/a2a/v1", json=_rpc("message/send", _message("say hello"))
    ).json()["result"]

    assert result["kind"] == "task"
    assert result["status"]["state"] == TaskState.completed.value
    assert result["status"]["message"]["parts"][0]["text"] == "Hello"
    # contextId is namespaced per caller so peers can't read each other's chats.
    assert result["contextId"].startswith("a2a:local")


def test_run_error_settles_task_as_failed(monkeypatch):
    _stub_agent(
        monkeypatch,
        [f"data: {json.dumps({'type': 'RUN_ERROR', 'message': 'model exploded'})}\n\n"],
    )

    result = client.post("/a2a/v1", json=_rpc("message/send", _message("go"))).json()[
        "result"
    ]

    assert result["status"]["state"] == TaskState.failed.value
    assert "model exploded" in result["status"]["message"]["parts"][0]["text"]


def test_context_id_is_namespaced_not_spoofable(monkeypatch):
    _stub_agent(monkeypatch, [_text_frame("ok")])

    result = client.post(
        "/a2a/v1",
        json=_rpc("message/send", _message("go", contextId="someone-elses-chat")),
    ).json()["result"]

    # A caller-supplied contextId lands under its own namespace, never at the root.
    assert result["contextId"] == "a2a:local:someone-elses-chat"


def test_message_stream_emits_sse_events(monkeypatch):
    _stub_agent(monkeypatch, [_text_frame("streamed")])

    with client.stream(
        "POST", "/a2a/v1", json=_rpc("message/stream", _message("go"))
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        payloads = [
            json.loads(line[6:])
            for line in response.iter_lines()
            if line.startswith("data: ")
        ]

    kinds = [p["result"]["kind"] for p in payloads]
    assert "status-update" in kinds
    assert "artifact-update" in kinds
    # The stream closes on a final event, and that event is terminal.
    final = [p["result"] for p in payloads if p["result"].get("final")]
    assert final and final[-1]["status"]["state"] == TaskState.completed.value


def test_tasks_get_returns_the_completed_task(monkeypatch):
    _stub_agent(monkeypatch, [_text_frame("done")])

    task_id = client.post("/a2a/v1", json=_rpc("message/send", _message("go"))).json()[
        "result"
    ]["id"]

    fetched = client.post("/a2a/v1", json=_rpc("tasks/get", {"id": task_id})).json()
    assert fetched["result"]["id"] == task_id
    assert fetched["result"]["status"]["state"] == TaskState.completed.value


def test_cancel_of_settled_task_is_not_cancelable(monkeypatch):
    _stub_agent(monkeypatch, [_text_frame("done")])

    task_id = client.post("/a2a/v1", json=_rpc("message/send", _message("go"))).json()[
        "result"
    ]["id"]

    response = client.post("/a2a/v1", json=_rpc("tasks/cancel", {"id": task_id}))
    assert response.json()["error"]["code"] == -32002
