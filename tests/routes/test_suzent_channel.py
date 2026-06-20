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


def test_inbound_streams_agent_reply(monkeypatch):
    import suzent.agent_manager as am
    import suzent.core.chat_processor as cp

    captured = {}

    class FakeProcessor:
        def process_turn(self, **kwargs):
            captured.update(kwargs)

            async def gen():
                yield 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"hi"}\n\n'
                yield "data: [DONE]\n\n"

            return gen()

    monkeypatch.setattr(cp, "ChatProcessor", FakeProcessor)
    monkeypatch.setattr(am, "build_agent_config", lambda *a, **k: {})

    client = TestClient(_app())
    r = client.post(
        "/channels/suzent/inbound", json={"from_id": "p1", "content": "hello"}
    )
    assert r.status_code == 200
    assert "hi" in r.text
    # Session is keyed by the peer (contact) id.
    assert captured["chat_id"] == "suzent:p1"
    assert captured["message_content"] == "hello"
    # Headless + auto so a remote peer's run doesn't block on approvals.
    assert captured["config_override"]["interaction_profile"] == "headless"
    assert captured["config_override"]["permission_mode"] == "auto"


def test_inbound_rejects_empty_content(monkeypatch):
    import suzent.agent_manager as am
    import suzent.core.chat_processor as cp

    monkeypatch.setattr(cp, "ChatProcessor", object)
    monkeypatch.setattr(am, "build_agent_config", lambda *a, **k: {})

    client = TestClient(_app())
    r = client.post("/channels/suzent/inbound", json={"from_id": "p1", "content": "  "})
    assert r.status_code == 400
