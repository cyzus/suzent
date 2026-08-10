"""
Tests for the Suzent agent-to-agent channel inbound route (Phase 1).
"""

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes.suzent_channel_routes import (
    suzent_channel_inbox,
    suzent_channel_inbound,
    suzent_channel_session,
    suzent_channel_stop,
)


def _app():
    return Starlette(
        routes=[
            Route("/channels/suzent/inbound", suzent_channel_inbound, methods=["POST"]),
            Route("/channels/suzent/inbox", suzent_channel_inbox, methods=["POST"]),
            Route("/channels/suzent/session", suzent_channel_session, methods=["GET"]),
            Route("/channels/suzent/stop", suzent_channel_stop, methods=["POST"]),
        ]
    )


def _authenticated_app():
    app = _app()
    record = {
        "device_id": "device-1",
        "display_name": "Laptop",
        "callback_url": "http://peer:25314",
    }
    app.state.node_manager = type(
        "NodeManager",
        (),
        {"device_store": type("Store", (), {"verify": lambda self, token: record})()},
    )()
    return app


class _FakeDB:
    """Minimal DB stub so the route's ensure/cleanup calls don't touch a real DB."""

    def __init__(self):
        self.created = []

    def ensure_channel_chat(self, chat_id, **kwargs):
        self.created.append((chat_id, kwargs))
        return True

    def get_chat(self, chat_id):
        return None  # after the turn, treated as empty → cleanup no-ops on None

    def delete_chat(self, chat_id, cascade_subagents=False):
        return True


def _patch_common(monkeypatch):
    import suzent.agent_manager as am
    import suzent.core.chat_processor as cp
    import suzent.database as dbmod

    monkeypatch.setattr(am, "build_agent_config", lambda *a, **k: {})
    monkeypatch.setattr(dbmod, "get_database", lambda: _FakeDB())
    return cp


def test_inbound_streams_agent_reply(monkeypatch):
    cp = _patch_common(monkeypatch)
    captured = {}

    class FakeProcessor:
        def process_turn(self, **kwargs):
            captured.update(kwargs)

            async def gen():
                yield 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"hi"}\n\n'
                yield "data: [DONE]\n\n"

            return gen()

    monkeypatch.setattr(cp, "ChatProcessor", FakeProcessor)

    # No token here (loopback in-process), so the caller must supply chat_id.
    client = TestClient(_app())
    r = client.post(
        "/channels/suzent/inbound",
        json={"chat_id": "suzent:p1", "content": "hello"},
    )
    assert r.status_code == 200
    assert "hi" in r.text
    assert captured["chat_id"] == "suzent:p1"
    # The visible message is the raw content; attribution is a hidden reminder.
    assert captured["message_content"] == "hello"
    reminders = captured.get("system_reminders") or []
    assert any("triggered remotely" in r.lower() for r in reminders)
    # Headless + auto so a remote peer's run doesn't block on approvals.
    assert captured["config_override"]["interaction_profile"] == "headless"
    assert captured["config_override"]["permission_mode"] == "auto"


def test_inbound_rejects_unidentified(monkeypatch):
    # No token AND no chat_id → can't key a session safely → 401, no chat.
    _patch_common(monkeypatch)
    client = TestClient(_app())
    r = client.post(
        "/channels/suzent/inbound", json={"from_id": "spoofed", "content": "hi"}
    )
    assert r.status_code == 401


def test_inbound_frames_run_error_on_failure(monkeypatch):
    # A turn that raises mid-stream must surface a RUN_ERROR frame (not a silent
    # end), matching the /chat/send drive loop.
    cp = _patch_common(monkeypatch)

    class FakeProcessor:
        def process_turn(self, **kwargs):
            async def gen():
                yield 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"partial"}\n\n'
                raise RuntimeError("boom")

            return gen()

    monkeypatch.setattr(cp, "ChatProcessor", FakeProcessor)
    client = TestClient(_app())
    r = client.post(
        "/channels/suzent/inbound",
        json={"chat_id": "suzent:p1", "content": "hi"},
    )
    assert r.status_code == 200
    assert "RUN_ERROR" in r.text
    assert "boom" in r.text


def test_inbound_rejects_empty_content(monkeypatch):
    _patch_common(monkeypatch)
    client = TestClient(_app())
    r = client.post(
        "/channels/suzent/inbound", json={"chat_id": "suzent:p1", "content": "  "}
    )
    assert r.status_code == 400


def test_authenticated_inbound_namespaces_caller_session_id(monkeypatch):
    cp = _patch_common(monkeypatch)
    captured = {}

    class FakeProcessor:
        def process_turn(self, **kwargs):
            captured.update(kwargs)

            async def gen():
                yield "data: [DONE]\n\n"

            return gen()

    monkeypatch.setattr(cp, "ChatProcessor", FakeProcessor)
    client = TestClient(_authenticated_app())

    response = client.post(
        "/channels/suzent/inbound",
        headers={"Authorization": "Bearer valid"},
        json={"chat_id": "workstream-1", "content": "hi"},
    )

    assert response.status_code == 200
    assert captured["chat_id"] == "suzent:device-1:workstream-1"


def test_authenticated_inbound_rejects_local_chat_id(monkeypatch):
    _patch_common(monkeypatch)
    client = TestClient(_authenticated_app())

    response = client.post(
        "/channels/suzent/inbound",
        headers={"Authorization": "Bearer valid"},
        json={"chat_id": "project:private-chat", "content": "hi"},
    )

    assert response.status_code == 403


def test_peer_inbox_persists_idempotently_before_ack(monkeypatch):
    import suzent.core.agent_inbox as inbox
    import suzent.database as dbmod

    database = _FakeDB()
    seen = {}

    def enqueue(**kwargs):
        created = kwargs["message_id"] not in seen
        seen.setdefault(kwargs["message_id"], kwargs)
        return {"message_id": kwargs["message_id"], "status": "pending"}, created

    monkeypatch.setattr(dbmod, "get_database", lambda: database)
    monkeypatch.setattr(inbox, "enqueue_agent_message", enqueue)
    client = TestClient(_authenticated_app())
    request = {
        "message_id": "msg-origin-1",
        "content": "Run the remote review",
    }

    first = client.post(
        "/channels/suzent/inbox",
        headers={"Authorization": "Bearer valid"},
        json=request,
    )
    second = client.post(
        "/channels/suzent/inbox",
        headers={"Authorization": "Bearer valid"},
        json=request,
    )

    assert first.status_code == 202
    assert first.json()["created"] is True
    assert second.status_code == 202
    assert second.json()["created"] is False
    assert len(seen) == 1
    queued = next(iter(seen.values()))
    assert queued["target_chat_id"] == "suzent:device-1"
    assert queued["payload"]["sender_label"] == "Laptop"


def test_peer_session_returns_only_authenticated_peer_chat(monkeypatch):
    import suzent.database as dbmod

    requested = []
    chat = type(
        "Chat",
        (),
        {"messages": [{"role": "user", "content": "Peer-owned message"}]},
    )()

    class FakeDatabase:
        def get_chat(self, chat_id):
            requested.append(chat_id)
            return chat

    monkeypatch.setattr(dbmod, "get_database", lambda: FakeDatabase())
    client = TestClient(_authenticated_app())

    response = client.get(
        "/channels/suzent/session",
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 200
    assert requested == ["suzent:device-1"]
    assert response.json()["messages"][0]["text"] == "Peer-owned message"


def test_peer_stop_targets_only_authenticated_peer_chat(monkeypatch):
    stopped = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.stop_stream",
        lambda chat_id, reason: stopped.append((chat_id, reason)) or True,
    )
    client = TestClient(_authenticated_app())

    response = client.post(
        "/channels/suzent/stop",
        headers={"Authorization": "Bearer valid"},
    )

    assert response.status_code == 200
    assert stopped[0][0] == "suzent:device-1"
