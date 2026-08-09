from __future__ import annotations

from typing import Any
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.nodes.base import NodeBase, NodeCapability
from suzent.nodes.manager import NodeManager
from suzent.nodes.peer_store import PeerGrantStore
from suzent.nodes.peer_files import PeerFileRegistry
from suzent.routes.node_routes import (
    invoke_peer,
    peer_invoke,
    proxy_peer_file,
    serve_peer_file,
    trigger_peer,
)


class FakeCameraNode(NodeBase):
    def __init__(self, file_path: str):
        super().__init__(
            "camera-node",
            "Camera",
            "test",
            [NodeCapability(name="camera.snap")],
        )
        self.file_path = file_path

    async def invoke(self, command, params=None, timeout=None):
        return {
            "success": True,
            "result": {"file": self.file_path, "format": "png"},
        }

    async def heartbeat(self):
        return True


def test_peer_invoke_registers_and_serves_camera_file(tmp_path):
    image_path = tmp_path / "snap.png"
    image_path.write_bytes(b"png-bytes")

    manager = NodeManager()
    manager.register_node(FakeCameraNode(str(image_path)))
    app = Starlette(
        routes=[
            Route("/nodes/peer-invoke", peer_invoke, methods=["POST"]),
            Route("/nodes/peer-files/{file_id}", serve_peer_file, methods=["GET"]),
        ]
    )
    app.state.node_manager = manager
    client = TestClient(app)

    response = client.post("/nodes/peer-invoke", json={"command": "camera.snap"})

    assert response.status_code == 200
    body = response.json()
    file_ref = body["result"]["file"]
    assert file_ref["id"].startswith("pf_")
    assert file_ref["url"] == f"/nodes/peer-files/{file_ref['id']}"
    assert file_ref["media_type"] == "image/png"
    assert file_ref["size"] == len(b"png-bytes")
    assert str(image_path) not in str(body)

    download = client.get(file_ref["url"])
    assert download.status_code == 200
    assert download.content == b"png-bytes"
    assert download.headers["content-type"].startswith("image/png")


def test_invoke_peer_rewrites_peer_file_reference(tmp_path, monkeypatch):
    store = PeerGrantStore(path=tmp_path / "peers.json")
    peer_id = store.add("Peer", "http://peer.example", "peer-token")

    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, Any]:
            return {
                "success": True,
                "result": {
                    "file": {
                        "id": "pf_123",
                        "url": "/nodes/peer-files/pf_123",
                        "name": "snap.png",
                        "media_type": "image/png",
                    }
                },
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            assert url == "http://peer.example/nodes/peer-invoke"
            assert headers == {"Authorization": "Bearer peer-token"}
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    app = Starlette(
        routes=[Route("/nodes/peers/{peer_id}/invoke", invoke_peer, methods=["POST"])]
    )
    app.state.peer_store = store
    client = TestClient(app)

    response = client.post(
        f"/nodes/peers/{peer_id}/invoke",
        json={"command": "camera.snap"},
    )

    assert response.status_code == 200
    file_ref = response.json()["result"]["file"]
    assert file_ref["peer_id"] == peer_id
    assert file_ref["url"] == f"/nodes/peers/{peer_id}/files/pf_123"


def test_proxy_peer_file_streams_from_peer(tmp_path, monkeypatch):
    store = PeerGrantStore(path=tmp_path / "peers.json")
    peer_id = store.add("Peer", "http://peer.example", "peer-token")

    class ByteStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"hello "
            yield b"peer"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.closed = False

        def build_request(self, method, url, headers=None):
            assert method == "GET"
            assert url == "http://peer.example/nodes/peer-files/pf_123"
            assert headers == {"Authorization": "Bearer peer-token"}
            return httpx.Request(method, url, headers=headers)

        async def send(self, request, stream=False):
            assert stream is True
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/plain",
                    "content-length": "10",
                    "content-disposition": 'attachment; filename="peer.txt"',
                },
                stream=ByteStream(),
                request=request,
            )

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    app = Starlette(
        routes=[
            Route(
                "/nodes/peers/{peer_id}/files/{file_id}",
                proxy_peer_file,
                methods=["GET"],
            )
        ]
    )
    app.state.peer_store = store
    client = TestClient(app)

    response = client.get(f"/nodes/peers/{peer_id}/files/pf_123")

    assert response.status_code == 200
    assert response.content == b"hello peer"
    assert response.headers["content-type"].startswith("text/plain")
    assert response.headers["content-disposition"] == 'attachment; filename="peer.txt"'


def test_proxy_peer_file_closes_client_when_send_fails(tmp_path, monkeypatch):
    store = PeerGrantStore(path=tmp_path / "peers.json")
    peer_id = store.add("Peer", "http://peer.example", "peer-token")
    clients = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.closed = False
            clients.append(self)

        def build_request(self, method, url, headers=None):
            return httpx.Request(method, url, headers=headers)

        async def send(self, request, stream=False):
            raise httpx.ConnectError("offline", request=request)

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    app = Starlette(
        routes=[
            Route(
                "/nodes/peers/{peer_id}/files/{file_id}",
                proxy_peer_file,
                methods=["GET"],
            )
        ]
    )
    app.state.peer_store = store
    client = TestClient(app)

    response = client.get(f"/nodes/peers/{peer_id}/files/pf_123")

    assert response.status_code == 502
    assert clients
    assert clients[0].closed is True


def test_transfer_grant_is_short_lived_and_use_limited(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("hello", encoding="utf-8")
    registry = PeerFileRegistry()

    artifact, token = registry.register_transfer(path)

    assert registry.authorize_transfer(artifact.file_id, "wrong") is None
    assert registry.authorize_transfer(artifact.file_id, token) == artifact
    assert registry.authorize_transfer(artifact.file_id, token) == artifact
    assert registry.authorize_transfer(artifact.file_id, token) is None


@pytest.mark.asyncio
async def test_serve_peer_file_accepts_transfer_token_from_remote(tmp_path):
    path = tmp_path / "report.txt"
    path.write_text("hello", encoding="utf-8")
    registry = PeerFileRegistry()
    artifact, token = registry.register_transfer(path)
    app = SimpleNamespace(
        state=SimpleNamespace(peer_file_registry=registry, node_manager=None)
    )

    wrong_request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": artifact.to_reference()["url"],
            "headers": [(b"authorization", b"Bearer wrong")],
            "path_params": {"file_id": artifact.file_id},
            "client": ("192.168.1.20", 50000),
            "app": app,
        }
    )
    wrong_response = await serve_peer_file(wrong_request)
    assert wrong_response.status_code == 404

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": artifact.to_reference()["url"],
            "headers": [(b"authorization", f"Bearer {token}".encode("latin-1"))],
            "path_params": {"file_id": artifact.file_id},
            "client": ("192.168.1.20", 50000),
            "app": app,
        }
    )
    response = await serve_peer_file(request)
    assert response.status_code == 200


def test_trigger_peer_sends_ephemeral_attachment_reference(tmp_path, monkeypatch):
    path = tmp_path / "notes.txt"
    path.write_text("peer notes", encoding="utf-8")
    store = PeerGrantStore(path=tmp_path / "peers.json")
    peer_id = store.add("Peer", "http://peer.example", "peer-token")
    sent: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

        async def aread(self):
            return b""

        async def aiter_lines(self):
            yield 'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"ok"}'

    class StreamContext:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *exc):
            return False

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def stream(self, method, url, json=None, headers=None):
            sent.update(method=method, url=url, json=json, headers=headers)
            return StreamContext()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        "suzent.routes.node_routes._my_base_for_peer",
        lambda _peer_url, _port: "http://192.168.1.10:25314",
    )
    app = Starlette(
        routes=[Route("/nodes/peers/{peer_id}/trigger", trigger_peer, methods=["POST"])]
    )
    app.state.peer_store = store
    app.state.server_port = 25314
    client = TestClient(app)

    response = client.post(
        f"/nodes/peers/{peer_id}/trigger",
        json={"prompt": "Read this", "attachments": [{"path": str(path)}]},
    )

    assert response.status_code == 200
    attachment = sent["json"]["attachments"][0]
    assert attachment["name"] == "notes.txt"
    assert attachment["size"] == len(b"peer notes")
    assert attachment["url"].startswith(
        "http://192.168.1.10:25314/nodes/peer-files/pf_"
    )
    assert attachment["token"]
    assert str(path) not in str(sent["json"])
