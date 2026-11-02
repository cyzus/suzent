"""Capabilities that depend on optional packages refresh without a restart.

camera.snap needs OpenCV, which the camera plugin installs into a running
server. The in-process LocalNode and outbound NodeHost connections must then
advertise it; the server only learns a NodeHost's capabilities from the
connect handshake, so the host reconnects.
"""

import asyncio
import json

import pytest
import websockets

from suzent.nodes import node_host
from suzent.nodes.local_node import LocalNode
from suzent.nodes.node_host import NodeHost
from suzent.nodes.outbound import OutboundConnectionManager


@pytest.fixture
def opencv(monkeypatch):
    """Toggle whether cv2 counts as installed."""
    state = {"cv2": False}
    monkeypatch.setattr(
        node_host, "_module_available", lambda module: state.get(module, True)
    )
    return state


def _names(caps):
    return [c["name"] for c in caps]


def test_local_node_refresh(opencv):
    node = LocalNode()
    assert "camera.snap" not in [c.name for c in node.capabilities]

    opencv["cv2"] = True
    names = node.refresh_capabilities()

    assert "camera.snap" in names
    assert "camera.snap" in [c.name for c in node.capabilities]
    assert "camera.snap" in node._handlers


@pytest.mark.asyncio
async def test_outbound_host_reconnects_with_new_capabilities(opencv):
    """End to end over a real WebSocket: the second handshake has camera.snap."""
    handshakes: list[dict] = []
    connected = asyncio.Event()

    async def gateway(ws):
        handshakes.append(json.loads(await ws.recv()))
        await ws.send(json.dumps({"type": "connected", "node_id": "n1"}))
        connected.set()
        async for _ in ws:
            pass

    async with websockets.serve(gateway, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        host = NodeHost(gateway_url=f"ws://127.0.0.1:{port}", display_name="T")
        host.device_token = ""
        manager = OutboundConnectionManager()
        manager._conns["gw"] = {"host": host, "task": asyncio.create_task(host.run())}
        try:
            await asyncio.wait_for(connected.wait(), 5)
            assert "camera.snap" not in _names(handshakes[0]["capabilities"])

            connected.clear()
            opencv["cv2"] = True
            await manager.refresh_capabilities()
            await asyncio.wait_for(connected.wait(), 5)

            assert len(handshakes) == 2
            assert "camera.snap" in _names(handshakes[1]["capabilities"])
        finally:
            await manager.stop_all()


@pytest.mark.asyncio
async def test_unchanged_capabilities_keep_the_connection(opencv):
    host = NodeHost(display_name="T")

    class _Ws:
        closed = False

        async def close(self):
            self.closed = True

    host._ws = _Ws()
    await host.refresh_capabilities()  # cv2 still missing: nothing changed

    assert host._ws.closed is False
