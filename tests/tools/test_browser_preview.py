import asyncio
from unittest.mock import AsyncMock
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.datastructures import URL
from starlette.websockets import WebSocketDisconnect

from suzent.routes import browser_routes
from suzent.auth_boundary import AuthBoundaryMiddleware
from suzent.tools.browser.config import BrowserSettings
from suzent.tools.browser.preview import PreviewFrames
from suzent.tools.browser.extension import bridge as bridge_module
from suzent.tools.browser.extension import session as session_module
from suzent.tools.browser.extension import routes as extension_routes


@pytest.mark.parametrize(
    "origin", ["http://evil.example", "http://127.0.0.1:25314", "http://localhost:8000"]
)
def test_loopback_auth_boundary_does_not_allow_hostile_preview_origin(
    origin: str,
) -> None:
    app = AuthBoundaryMiddleware(
        Starlette(
            routes=[
                WebSocketRoute("/ws/browser", browser_routes.browser_websocket_endpoint)
            ]
        )
    )
    with TestClient(
        app, base_url="http://127.0.0.1:25314", client=("127.0.0.1", 50000)
    ) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/browser", headers={"Origin": origin}):
                pytest.fail("An untrusted page must not receive a preview connection")


async def test_preview_retains_only_latest_pending_frame() -> None:
    waiting = asyncio.Event()
    client = AsyncMock()

    async def send(_: dict) -> None:
        await waiting.wait()

    client.send_json.side_effect = send
    frames = PreviewFrames([client])
    frames.offer({"data": "first"})
    await asyncio.sleep(0)
    task = frames.task
    for index in range(1000):
        frames.offer({"data": str(index)})
    assert frames.task is task
    assert frames.pending == {"data": "999"}
    waiting.set()
    await task
    assert [call.args[0]["data"] for call in client.send_json.call_args_list] == [
        "first",
        "999",
    ]
    await frames.clear()
    assert frames.task is None


async def test_preview_close_cancels_blocked_sender() -> None:
    async def send(_: dict) -> None:
        await asyncio.Event().wait()

    client = AsyncMock()
    client.send_json.side_effect = send
    frames = PreviewFrames([client])
    frames.offer({"data": "frame"})
    await asyncio.sleep(0)
    await asyncio.wait_for(frames.clear(), 0.5)
    assert frames.task is None
    assert frames.pending is None


async def test_status_and_focus_do_not_start_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        browser_routes.BrowserSettings,
        "load",
        lambda: BrowserSettings(connection_mode="extension"),
    )
    monkeypatch.setattr(browser_routes.bridge, "socket", object())
    request = AsyncMock(
        return_value={"selected": True, "title": "Example", "browser": "Edge"}
    )
    monkeypatch.setattr(browser_routes.bridge, "request", request)
    app = Starlette(
        routes=[
            Route(
                "/browser/status",
                browser_routes.browser_status_endpoint,
                methods=["GET", "POST"],
            )
        ]
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        assert (await client.get("/browser/status")).status_code == 403
        result = await client.get(
            "/browser/status", headers={"Origin": "tauri://localhost"}
        )
        assert result.json()["title"] == "Example"
        assert (await client.post("/browser/status")).status_code == 403
        assert (
            await client.post(
                "/browser/status",
                headers={"X-Suzent-Browser-Setup": "1", "Origin": "tauri://localhost"},
            )
        ).status_code == 200
        assert (
            await client.get(
                "/browser/status", headers={"Origin": "https://evil.example"}
            )
        ).status_code == 403
        assert (
            await client.get(
                "/browser/status", headers={"Sec-Fetch-Site": "same-origin"}
            )
        ).status_code == 403
    assert [call.args[0] for call in request.call_args_list] == [
        "status",
        "status",
        "focus",
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "https://evil.example",
        "http://evil.example",
        "null",
        "http://localhost:9999",
        "http://127.0.0.1:25314",
        "http://localhost:8000",
    ],
)
async def test_preview_rejects_untrusted_origins_before_registration(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    manager = AsyncMock()
    monkeypatch.setattr(
        browser_routes.BrowserSessionManager, "get_instance", lambda: manager
    )
    websocket = AsyncMock()
    websocket.client = SimpleNamespace(host="127.0.0.1")
    websocket.url = URL("ws://127.0.0.1:25314/ws/browser")
    websocket.headers = {"origin": origin}
    await browser_routes.browser_websocket_endpoint(websocket)
    websocket.close.assert_awaited_once_with(code=1008)
    manager.add_client.assert_not_called()
    websocket.receive_json.assert_not_called()


@pytest.mark.parametrize(
    "origin",
    [
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
        "http://localhost:18080",
        "http://127.0.0.1:18080",
    ],
)
async def test_preview_allows_local_ui_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, origin: str
) -> None:
    manager = AsyncMock()
    manager._playwright = None
    manager._action_lock = asyncio.Lock()
    extension = AsyncMock()
    extension.clients = []
    monkeypatch.setattr(
        browser_routes.BrowserSessionManager, "get_instance", lambda: manager
    )
    monkeypatch.setattr(browser_routes, "extension_session", extension)
    monkeypatch.setattr(
        browser_routes.BrowserSettings,
        "load",
        lambda: BrowserSettings(connection_mode="extension"),
    )
    websocket = AsyncMock()
    websocket.client = SimpleNamespace(host="127.0.0.1")
    websocket.url = URL("ws://127.0.0.1:25314/ws/browser")
    websocket.headers = {"origin": origin}
    websocket.receive_json.side_effect = WebSocketDisconnect()
    await browser_routes.browser_websocket_endpoint(websocket)
    manager.add_client.assert_awaited_once_with(websocket)
    extension.start_streaming.assert_awaited_once()
    manager.remove_client.assert_awaited_once_with(websocket)
    extension.remove_client.assert_awaited_once_with(websocket)


@pytest.mark.parametrize("close_fails", [False, True])
async def test_extension_timeout_resets_session_and_replaces_pending_screenshot(
    monkeypatch: pytest.MonkeyPatch, close_fails: bool
) -> None:
    connection = bridge_module.ExtensionBridge()
    socket = AsyncMock()
    if close_fails:
        socket.close.side_effect = RuntimeError("Already closed")
    connection.socket = socket
    monkeypatch.setattr(bridge_module, "REQUEST_TIMEOUT", 0.01)
    monkeypatch.setattr(session_module, "bridge", connection)
    session = session_module.ExtensionSession()
    session.selected = "tab-1"
    session.streaming = True
    session.world = 42
    session.refs["old-ref"] = (0, {})
    client = AsyncMock()

    async def send(message: dict) -> None:
        if message["type"] == "frame":
            await asyncio.Event().wait()

    client.send_json.side_effect = send
    session.clients.append(client)
    session.frames.offer({"type": "frame", "data": "old screenshot"})
    with pytest.raises(ValueError, match="timed out"):
        await connection.request("cdp", method="Runtime.evaluate")
    assert connection.socket is None
    assert session.selected is None
    assert not session.streaming
    assert session.world is None
    assert not session.refs
    assert not connection._pending
    await session.frames.task
    client.send_json.assert_awaited_with({"type": "reset"})
    socket.send_json.assert_awaited_once()
    await session.frames.clear()


@pytest.mark.parametrize(
    "error", [RuntimeError("Already closed"), OSError("Broken pipe")]
)
async def test_replacement_succeeds_when_old_socket_cannot_close(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    connection = bridge_module.ExtensionBridge()
    old = AsyncMock()
    old.close.side_effect = error
    connection.socket = old
    monkeypatch.setattr(session_module, "bridge", connection)
    session = session_module.ExtensionSession()
    session.selected = "tab-old"
    session.streaming = True
    session.refs["old"] = (0, {})
    pending = asyncio.get_running_loop().create_future()
    connection._pending[1] = pending
    monkeypatch.setattr(extension_routes, "bridge", connection)
    monkeypatch.setattr(extension_routes, "install_native_host", lambda _: None)
    monkeypatch.setattr(connection, "authenticate", lambda *_: True)
    incoming = AsyncMock()
    incoming.client = SimpleNamespace(host="127.0.0.1")
    incoming.headers = {"origin": "chrome-extension://" + "a" * 32}
    incoming.receive_json.return_value = {"token": "a" * 43}
    incoming.receive_text.side_effect = WebSocketDisconnect()

    async def ready(message: dict) -> None:
        assert message == {"type": "ready"}
        assert connection.socket is incoming
        assert session.selected is None
        assert not session.streaming
        assert not session.refs

    incoming.send_json.side_effect = ready
    await extension_routes.extension_websocket(incoming)
    incoming.send_json.assert_awaited_once_with({"type": "ready"})
    assert isinstance(pending.exception(), ValueError)
    assert not connection._pending
