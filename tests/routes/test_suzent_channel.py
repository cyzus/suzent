"""
Tests for the Suzent agent-to-agent channel inbound route (Phase 1).
"""

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes.suzent_channel_routes import suzent_channel_inbound


def _app():
    return Starlette(
        routes=[
            Route("/channels/suzent/inbound", suzent_channel_inbound, methods=["POST"])
        ]
    )


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
    # Content is framed with remote attribution, but carries the original text.
    assert "hello" in captured["message_content"]
    assert "Triggered remotely" in captured["message_content"]
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


def test_inbound_rejects_empty_content(monkeypatch):
    _patch_common(monkeypatch)
    client = TestClient(_app())
    r = client.post(
        "/channels/suzent/inbound", json={"chat_id": "suzent:p1", "content": "  "}
    )
    assert r.status_code == 400
