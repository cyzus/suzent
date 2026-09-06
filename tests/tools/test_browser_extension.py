import asyncio
import io
import socket
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

from suzent.config.paths import PROJECT_DIR

import pytest
import uvicorn
from playwright.async_api import async_playwright
from playwright.async_api import Error as PlaywrightError
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from suzent.tools.browser.extension import bridge as bridge_module
from suzent.tools.browser.extension import routes as extension_routes
from suzent.tools.browser.extension.bridge import ExtensionBridge, bridge
from suzent.tools.browser.extension.routes import (
    extension_settings,
    extension_connect_page,
    extension_download,
    extension_websocket,
)
from suzent.tools.browser.extension.session import session
from suzent.tools.browser.config import BrowserCommand
from suzent.tools.browser.config import BrowserSettings
from suzent.tools.browser.tool import BrowserSessionManager, BrowsingTool


@pytest.fixture(autouse=True)
def isolate_pairing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_module, "USER_CONFIG_DIR", tmp_path)
    bridge._pairing = None
    monkeypatch.setattr(extension_routes, "install_native_host", lambda _: None)


def test_pairing_is_bound_to_extension_and_revocable() -> None:
    connection = ExtensionBridge()
    token = connection.create_pairing()
    origin = "chrome-extension://" + "a" * 32
    assert not connection.authenticate("invalid", origin)
    assert connection.authenticate(token, origin)
    assert connection.authenticate(token, origin)
    assert not connection.authenticate(token, "chrome-extension://" + "b" * 32)
    next_token = connection.create_pairing()
    assert connection.authenticate(next_token, origin)
    assert not connection.authenticate(token, origin)


def test_expired_pairing_cannot_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    connection = ExtensionBridge()
    token = connection.create_pairing()
    monkeypatch.setattr(bridge_module.time, "monotonic", lambda: 10**20)
    assert not connection.authenticate(token, "chrome-extension://" + "a" * 32)


def app() -> Starlette:
    return Starlette(
        routes=[
            Route(
                "/browser/extension",
                extension_settings,
                methods=["GET", "POST", "DELETE"],
            ),
            Route("/browser/extension/connect", extension_connect_page),
            Route("/browser/extension/download", extension_download),
            WebSocketRoute("/ws/browser-extension", extension_websocket),
            Route(
                "/test",
                lambda _: HTMLResponse(
                    '<title>Extension test</title><label>Name<input id="name"></label><button onclick="this.textContent=\'Done\'">Click</button>'
                ),
            ),
        ]
    )


def test_setup_rejects_untrusted_web_origin_and_requires_header() -> None:
    with TestClient(app()) as client:
        assert (
            client.post(
                "/browser/extension",
                headers={
                    "Origin": "https://evil.example",
                    "X-Suzent-Browser-Setup": "1",
                },
            ).status_code
            == 403
        )
        assert client.post("/browser/extension").status_code == 403
        result = client.post(
            "/browser/extension", headers={"X-Suzent-Browser-Setup": "1"}
        )
        assert result.status_code == 200 and "#" in result.json()["url"]
        archive = client.get("/browser/extension/download")
        with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
            assert {
                "manifest.json",
                "worker.js",
                "pair.js",
                "_locales/en/messages.json",
            } <= set(package.namelist())


def test_setup_exposes_checkout_folder_and_rejects_missing_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(extension_routes, "PROJECT_DIR", tmp_path)
    with TestClient(app()) as client:
        status = client.get("/browser/extension")
        assert status.json()["source_dir"] == str(tmp_path / "extensions" / "browser")
        assert client.get("/browser/extension/download").status_code == 404


def test_download_rejects_incomplete_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "extensions" / "browser"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(extension_routes, "PROJECT_DIR", tmp_path)
    with TestClient(app()) as client:
        response = client.get("/browser/extension/download")
        assert response.status_code == 503
        assert response.headers["content-type"] == "application/json"
        assert "content-disposition" not in response.headers


async def test_disconnect_fails_pending_commands_without_replay() -> None:
    connection = ExtensionBridge()
    connection.socket = AsyncMock()
    pending = asyncio.create_task(connection.request("open", url="https://example.com"))
    await asyncio.sleep(0)
    await connection.disconnected()
    with pytest.raises(ValueError, match="disconnected"):
        await pending
    assert not connection._pending


async def test_native_tool_routes_extension_mode_without_launching_playwright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        BrowserSettings, "load", lambda: BrowserSettings(connection_mode="extension")
    )
    manager = BrowserSessionManager()
    tool = BrowsingTool()
    tool.session_mgr = manager
    monkeypatch.setattr(bridge, "request", AsyncMock(return_value=[]))
    result = await tool._execute("tabs")
    assert result.success
    bridge.request.assert_awaited_once_with("tabs")
    assert manager._playwright is None


def test_websocket_rejects_websites_and_invalid_pairing() -> None:
    with TestClient(app()) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws/browser-extension", headers={"Origin": "http://evil.example"}
            ):
                pass
        with client.websocket_connect(
            "/ws/browser-extension",
            headers={"Origin": "chrome-extension://" + "a" * 32},
        ) as ws:
            ws.send_json({"token": "a" * 43})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()


@pytest.mark.parametrize("browser_channel", ["chromium", "msedge"])
async def test_real_extension_pair_actions_preview_and_disconnect(
    tmp_path: Path,
    browser_channel: str,
) -> None:
    from suzent.tools.browser.detection import available_browsers

    if not available_browsers()[browser_channel]:
        pytest.skip("Browser is not installed")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app(), log_level="error", lifespan="off"))
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    assets = PROJECT_DIR / "extensions" / "browser"
    try:
        async with async_playwright() as playwright:
            try:
                browser = await playwright.chromium.launch_persistent_context(
                    str(tmp_path / "profile"),
                    channel=browser_channel,
                    headless=True,
                    args=[
                        f"--disable-extensions-except={assets}",
                        f"--load-extension={assets}",
                    ],
                )
            except PlaywrightError as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip("Install Playwright Chromium to run the extension test")
                raise
            try:
                page = browser.pages[0]
                await page.goto(f"http://127.0.0.1:{port}/test")
                pairing = await browser.new_page()
                token = bridge.create_pairing()
                await pairing.goto(
                    f"http://127.0.0.1:{port}/browser/extension/connect#{token}"
                )
                for _ in range(100):
                    if bridge.socket:
                        break
                    await asyncio.sleep(0.05)
                assert bridge.socket is not None, await pairing.inner_text("body")
                result = await session.execute(BrowserCommand(command="tabs"))
                tab = next(
                    tab
                    for tab in result.metadata["tabs"]
                    if tab["url"].endswith("/test")
                )
                await session.execute(
                    BrowserCommand(command="select_tab", arguments=[tab["id"]])
                )
                assert not session.streaming
                status = await bridge.request("status")
                assert status["title"] == "Extension test"
                assert status["selected"]
                await bridge.request("focus")
                worker = browser.service_workers[0]
                assert (
                    await worker.evaluate(
                        "async () => (await chrome.tabs.query({active:true, lastFocusedWindow:true}))[0].url"
                    )
                    == page.url
                )
                result = await session.execute(BrowserCommand(command="snapshot"))
                assert result.success
                input_ref = next(
                    ref
                    for ref, (_, item) in session.refs.items()
                    if item["tag"] == "input"
                )
                button_ref = next(
                    ref
                    for ref, (_, item) in session.refs.items()
                    if item["tag"] == "button"
                )
                await session.execute(
                    BrowserCommand(
                        command="fill", arguments=[input_ref, "private text"]
                    )
                )
                assert await page.locator("input").input_value() == "private text"
                await session.execute(
                    BrowserCommand(command="click", arguments=[button_ref])
                )
                assert await page.locator("button").inner_text() == "Done"
                result = await session.execute(BrowserCommand(command="snapshot"))
                assert "private text" not in result.message
                with pytest.raises(ValueError, match="expired"):
                    await session.execute(
                        BrowserCommand(command="click", arguments=[button_ref])
                    )
                preview = AsyncMock()
                session.clients.append(preview)
                await session.start_streaming()
                for _ in range(100):
                    if preview.send_json.called:
                        break
                    await asyncio.sleep(0.05)
                assert preview.send_json.called
                assert preview.send_json.call_args.args[0]["type"] == "frame"
                await session.remove_client(preview)
                assert not session.streaming
                assert session.frames.task is None
                await session.close()
                assert not page.is_closed()
                assert await page.locator("input").input_value() == "private text"
                await bridge.revoke()
                assert bridge.socket is None
            finally:
                session.clients.clear()
                await session.close()
                await browser.close()
    finally:
        server.should_exit = True
        await serving
        listener.close()
