"""Plugin-gated capabilities refresh without a restart.

camera.snap needs OpenCV, installed by the camera plugin into a running
server, and the plugin being enabled. The in-process LocalNode and outbound
NodeHost connections must follow both; the server only learns a NodeHost's
capabilities from the connect handshake, so the host reconnects.
"""

import asyncio
import json

import pytest
import websockets

import suzent.plugins
from suzent.nodes import node_host
from suzent.nodes.local_node import LocalNode
from suzent.nodes.node_host import NodeHost
from suzent.nodes.outbound import OutboundConnectionManager


@pytest.fixture
def camera(monkeypatch):
    """Toggle whether OpenCV is installed and whether the plugin is enabled."""
    state = {"cv2": False, "plugin": False}
    monkeypatch.setattr(
        node_host,
        "_module_available",
        lambda module: state["cv2"] if module == "cv2" else True,
    )
    monkeypatch.setattr(
        node_host, "_enabled_plugins", lambda: {"camera"} if state["plugin"] else set()
    )
    return state


def _names(caps):
    return [c["name"] for c in caps]


def test_local_node_follows_install_and_removal(camera):
    node = LocalNode()
    assert "camera.snap" not in [c.name for c in node.capabilities]

    camera.update(cv2=True, plugin=True)  # plugin installed
    assert "camera.snap" in node.refresh_capabilities()
    assert "camera.snap" in node._handlers

    camera["plugin"] = False  # removed; OpenCV stays until the next upgrade
    assert "camera.snap" not in node.refresh_capabilities()
    assert "camera.snap" not in node._handlers


def test_plugin_state_errors_fail_closed(monkeypatch):
    def unreadable():
        raise RuntimeError("plugins.json unreadable")

    monkeypatch.setattr(suzent.plugins, "get_plugin_manager", unreadable)
    monkeypatch.setattr(node_host, "_module_available", lambda module: True)

    assert node_host._enabled_plugins() == set()
    assert "camera.snap" not in node_host.available_handlers()
    assert "speaker.speak" in node_host.available_handlers()


@pytest.mark.asyncio
async def test_outbound_host_reconnects_with_new_capabilities(camera):
    """Over a real WebSocket: each change produces a new handshake."""
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
            camera.update(cv2=True, plugin=True)
            await manager.refresh_capabilities()
            await asyncio.wait_for(connected.wait(), 5)
            assert "camera.snap" in _names(handshakes[1]["capabilities"])

            connected.clear()
            camera["plugin"] = False
            await manager.refresh_capabilities()
            await asyncio.wait_for(connected.wait(), 5)
            assert "camera.snap" not in _names(handshakes[2]["capabilities"])
            assert "camera.snap" not in host._handlers
        finally:
            await manager.stop_all()


@pytest.mark.asyncio
async def test_unchanged_capabilities_keep_the_connection(camera):
    host = NodeHost(display_name="T")

    class _Ws:
        closed = False

        async def close(self):
            self.closed = True

    host._ws = _Ws()
    await host.refresh_capabilities()  # nothing changed

    assert host._ws.closed is False
