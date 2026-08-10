from types import SimpleNamespace

import httpx
import pytest

from suzent.nodes.agent_transport import PeerAgentTransport, PeerAgentTransportError


class FakePeerStore:
    def __init__(self, mode: str = "trigger"):
        self.peer = {
            "name": "Laptop",
            "base_url": "http://peer:25314",
            "token": "secret-token",
            "mode": mode,
            "added_at": "2026-01-01T00:00:00+00:00",
        }

    def get(self, peer_id):
        return dict(self.peer) if peer_id == "peer-1" else None

    def list_peers(self):
        return [{"peer_id": "peer-1", **self.peer}]


def test_transport_lists_stable_peer_agent_addresses():
    agents = PeerAgentTransport(FakePeerStore()).list_agents()

    assert agents[0]["agent_id"] == "peer:peer-1"
    assert agents[0]["kind"] == "remote"
    assert agents[0]["status"] == "ready"


def test_transport_rejects_paused_peer():
    transport = PeerAgentTransport(FakePeerStore(mode="paused"))

    with pytest.raises(PeerAgentTransportError, match="paused"):
        transport.resolve("peer:peer-1")


def test_transport_enqueue_reuses_agent_message_queue(monkeypatch):
    captured = {}

    def enqueue(**kwargs):
        captured.update(kwargs)
        return {"message_id": "msg-1", "status": "pending"}, True

    monkeypatch.setattr("suzent.core.agent_inbox.enqueue_agent_message", enqueue)

    PeerAgentTransport(FakePeerStore()).enqueue(
        agent_id="peer:peer-1",
        sender_chat_id="chat-1",
        content="Review remotely",
    )

    assert captured["transport"] == "suzent_peer"
    assert captured["destination_peer_id"] == "peer-1"
    assert captured["target_chat_id"] == "peer:peer-1"
    assert captured["max_attempts"] == 48


@pytest.mark.asyncio
async def test_transport_delivery_acks_only_remote_persistence(monkeypatch):
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            captured.update(method=method, url=url, **kwargs)
            return SimpleNamespace(
                status_code=202,
                json=lambda: {"accepted": True, "message_id": "msg-1"},
            )

    monkeypatch.setattr(
        "suzent.nodes.agent_transport.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )
    message = {
        "message_id": "msg-1",
        "destination_peer_id": "peer-1",
        "content": "Review remotely",
    }

    await PeerAgentTransport(FakePeerStore()).deliver(message)

    assert captured["url"] == "http://peer:25314/channels/suzent/inbox"
    assert captured["headers"] == {"Authorization": "Bearer secret-token"}
    assert captured["json"] == {
        "message_id": "msg-1",
        "content": "Review remotely",
    }


@pytest.mark.asyncio
async def test_transport_normalizes_offline_network_errors(monkeypatch):
    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def request(self, method, url, **kwargs):
            raise httpx.ConnectError("offline", request=httpx.Request(method, url))

    monkeypatch.setattr(
        "suzent.nodes.agent_transport.httpx.AsyncClient",
        lambda **kwargs: FailingClient(),
    )

    with pytest.raises(PeerAgentTransportError, match="ConnectError"):
        await PeerAgentTransport(FakePeerStore()).read("peer:peer-1")
