"""
End-to-end: a real NodeHost connecting (outbound) to a real running server in
approve mode must produce a pending entry on the server and a 'pending' status
on the node. This exercises the live WebSocket handshake that the unit tests
(which call _authorize_node directly) do not.
"""

import asyncio

import pytest
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute

from suzent.nodes.device_store import DeviceTokenStore
from suzent.nodes.manager import NodeManager
from suzent.routes.node_routes import (
    list_pending_nodes,
    node_websocket_endpoint,
)


def _build_app(tmp_path):
    app = Starlette(
        routes=[
            WebSocketRoute("/ws/node", node_websocket_endpoint),
            Route("/nodes/pending", list_pending_nodes, methods=["GET"]),
        ]
    )
    app.state.node_manager = NodeManager(
        device_store=DeviceTokenStore(path=tmp_path / "server_devices.json")
    )
    return app


@pytest.mark.asyncio
async def test_outbound_node_appears_pending(tmp_path, monkeypatch):
    # Don't touch the real user config dir for the node's saved token.
    from suzent.nodes import node_host

    monkeypatch.setattr(node_host, "_load_device_token", lambda url: "")
    monkeypatch.setattr(node_host, "_save_device_token", lambda url, tok: None)

    app = _build_app(tmp_path)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    serve_task = asyncio.create_task(server.serve())
    try:
        # Wait for the server to bind and learn its ephemeral port.
        for _ in range(200):
            if server.started and server.servers:
                break
            await asyncio.sleep(0.02)
        assert server.started
        port = server.servers[0].sockets[0].getsockname()[1]

        host = node_host.NodeHost(
            gateway_url=f"ws://127.0.0.1:{port}/ws/node",
            display_name="IntegrationNode",
        )
        host_task = asyncio.create_task(host.run())
        try:
            mgr = app.state.node_manager
            # The node should land in the server's pending list…
            for _ in range(200):
                if mgr.list_pending():
                    break
                await asyncio.sleep(0.02)
            pending = mgr.list_pending()
            assert len(pending) == 1, f"expected 1 pending, got {pending}"
            assert pending[0]["display_name"] == "IntegrationNode"

            # …and the node should report 'pending' with the same code.
            for _ in range(100):
                if host.status == "pending":
                    break
                await asyncio.sleep(0.02)
            assert host.status == "pending"
            assert host.pairing_code == pending[0]["pairing_code"]

            # Approving it should connect the node and mint a token.
            ok, token = mgr.approve_pending(pending[0]["pairing_code"])
            assert ok and token
            for _ in range(100):
                if host.status == "connected":
                    break
                await asyncio.sleep(0.02)
            assert host.status == "connected"
        finally:
            host.stop()
            host_task.cancel()
            try:
                await host_task
            except (asyncio.CancelledError, Exception):
                pass
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(serve_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
            pass
