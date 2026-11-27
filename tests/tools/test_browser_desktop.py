import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import Error as PlaywrightError
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from suzent.tools.browser import config as browser_config
from suzent.tools.browser import desktop
from suzent.tools.browser import tool as tool_module
from suzent.tools.browser.config import BrowserCommand, BrowserSettings
from suzent.tools.browser.tool import BrowserSessionManager, BrowsingTool


@pytest.fixture(autouse=True)
def isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(desktop, "RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(browser_config, "USER_CONFIG_DIR", tmp_path)
    monkeypatch.delenv("SUZENT_BROWSER_CONNECTION_MODE", raising=False)
    monkeypatch.setattr(desktop, "desktop_bridge", desktop.DesktopBridge())


def app() -> Starlette:
    return Starlette(
        routes=[
            WebSocketRoute("/ws/browser-desktop", desktop.desktop_browser_websocket)
        ]
    )


def test_token_is_private_to_the_user_and_removed_on_shutdown(tmp_path: Path) -> None:
    connection = desktop.desktop_bridge
    connection.publish(4321)
    path = tmp_path / "desktop-browser-4321.token"
    token = path.read_text(encoding="utf-8")
    assert connection.authenticate(token)
    assert not connection.authenticate("x" * 43)
    if sys.platform != "win32":
        assert os.stat(path).st_mode & 0o777 == 0o600
    connection.unpublish()
    assert not path.exists()


def test_the_app_connects_with_the_token_and_websites_cannot(tmp_path: Path) -> None:
    connection = desktop.desktop_bridge
    connection.publish(4321)
    token = (tmp_path / "desktop-browser-4321.token").read_text(encoding="utf-8")
    with TestClient(app()) as client:
        # A web page always sends an Origin and never reads the token file.
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws/browser-desktop", headers={"origin": "https://evil.example"}
            ) as socket:
                socket.send_json({"token": token})
                socket.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/browser-desktop") as socket:
                socket.send_json({"token": "A" * 43})
                socket.receive_json()
        assert desktop.effective_mode("desktop") == "managed"
        with client.websocket_connect("/ws/browser-desktop") as socket:
            socket.send_json({"token": token})
            assert socket.receive_json() == {"type": "ready", "persistent": True}
            assert desktop.effective_mode("desktop") == "desktop"
            assert desktop.effective_mode("managed") == "managed"
        assert desktop.effective_mode("desktop") == "managed"


async def test_tool_uses_the_app_browser_while_the_app_is_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        BrowserSettings, "load", lambda: BrowserSettings(connection_mode="desktop")
    )
    manager = BrowserSessionManager()
    tool = BrowsingTool()
    tool.session_mgr = manager
    connection = desktop.desktop_bridge
    session = desktop.BridgeSession(connection)
    monkeypatch.setattr(desktop, "desktop_session", session)
    connection.socket = AsyncMock()
    monkeypatch.setattr(connection, "request", AsyncMock(return_value=[]))
    result = await tool._execute("tabs")
    assert result.success
    connection.request.assert_awaited_once_with("tabs")
    assert manager._playwright is None


async def test_tool_falls_back_to_a_managed_browser_without_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        BrowserSettings, "load", lambda: BrowserSettings(connection_mode="desktop")
    )
    manager = BrowserSessionManager()
    tool = BrowsingTool()
    tool.session_mgr = manager
    monkeypatch.setattr(manager, "ensure_session", AsyncMock(return_value=False))
    monkeypatch.setattr(
        manager,
        "tabs",
        AsyncMock(return_value=tool_module.ToolResult.success_result("")),
    )
    result = await tool._execute("tabs")
    assert result.success
    manager.ensure_session.assert_awaited_once()


async def test_installed_chrome_is_used_before_downloading_chromium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BrowserSessionManager(BrowserSettings(channel="chromium"))
    launched: list[str | None] = []

    async def launch(headless: bool | None, channel: str | None = None) -> None:
        launched.append(channel)
        if channel is None:
            raise PlaywrightError("Executable doesn't exist at /x/chrome")

    monkeypatch.setattr(manager, "_launch_context", launch)
    monkeypatch.setattr(
        tool_module,
        "available_browsers",
        lambda: {"chromium": True, "chrome": False, "msedge": True},
    )
    install = AsyncMock()
    monkeypatch.setattr(tool_module, "install_chromium", install)
    await manager._launch_with_fallback(True)
    assert launched == [None, "msedge"]
    install.assert_not_awaited()


async def test_chromium_is_downloaded_only_when_no_browser_is_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BrowserSessionManager(BrowserSettings(channel="chromium"))
    attempts = 0

    async def launch(headless: bool | None, channel: str | None = None) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PlaywrightError("Executable doesn't exist at /x/chrome")

    monkeypatch.setattr(manager, "_launch_context", launch)
    monkeypatch.setattr(
        tool_module,
        "available_browsers",
        lambda: {"chromium": True, "chrome": False, "msedge": False},
    )
    install = AsyncMock()
    monkeypatch.setattr(tool_module, "install_chromium", install)
    await manager._launch_with_fallback(True)
    install.assert_awaited_once()
    assert attempts == 2


async def test_page_changing_actions_return_the_new_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = BrowsingTool()
    calls: list[str] = []

    async def run(command: str, arguments: list[str] | None = None, site=None):
        calls.append(command)
        if command == "snapshot":
            return tool_module.ToolResult.success_result(
                "[Page: Next]\n@g2e0: <button> Buy", metadata={"snapshot_id": 2}
            )
        return tool_module.ToolResult.success_result(f"{command} completed.")

    monkeypatch.setattr(tool, "_run", run)
    monkeypatch.setattr(tool_module, "OBSERVE_DELAY", 0)
    clicked = await tool._execute("click", ["@g1e0"])
    assert calls == ["click", "snapshot"]
    assert "@g2e0: <button> Buy" in clicked.message
    assert clicked.metadata["snapshot"] == {"snapshot_id": 2}
    calls.clear()
    filled = await tool._execute("fill", ["@g2e0", "x"])
    assert calls == ["fill"]
    assert filled.message == "fill completed."


async def test_agent_tabs_open_and_close_in_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = desktop.desktop_bridge
    session = desktop.BridgeSession(connection)
    connection.socket = AsyncMock()
    replies = {"new": {"id": "tab-2", "url": "https://a.example/"}}
    replies["close"] = {"selected": "tab-1"}
    calls: list[tuple] = []

    async def request(action: str, **params):
        calls.append((action, params))
        return replies.get(action, {})

    monkeypatch.setattr(connection, "request", request)
    monkeypatch.setattr(session, "start_streaming", AsyncMock())
    opened = await session.execute(
        BrowserCommand(command="new_tab", arguments=["a.example"])
    )
    assert opened.success
    assert calls[0] == ("new", {"url": "https://a.example"})
    assert session.selected == "tab-2"
    await session.execute(BrowserCommand(command="close_tab", arguments=["tab-2"]))
    assert calls[1] == ("close", {"id": "tab-2"})
    assert session.selected == "tab-1"


async def test_the_agent_follows_the_tab_the_user_picks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = desktop.desktop_bridge
    connection.socket = AsyncMock()
    connection.generation = 4
    session = desktop.BridgeSession(connection)
    session.selected = "tab-1"
    session.refs = {"@g1e0": ("node", {})}
    session.clients = [AsyncMock()]
    session.streaming = True
    cdp = AsyncMock(return_value={})
    monkeypatch.setattr(session, "cdp", cdp)
    # The user picks a tab before the agent's first command on this connection.
    await session.on_event("selected", {"id": "tab-3"})
    assert session.selected == "tab-3"
    assert session.refs == {}
    await session._restream
    cdp.assert_awaited_once()
    assert cdp.await_args.args == ("Page.startScreencast",)
    monkeypatch.setattr(session, "snapshot", AsyncMock(return_value="page"))
    assert await session.execute(BrowserCommand(command="snapshot")) == "page"


async def test_your_own_browser_cannot_open_tabs_for_the_agent() -> None:
    from suzent.tools.browser.extension.bridge import ExtensionBridge

    connection = ExtensionBridge()
    connection.socket = AsyncMock()
    session = desktop.BridgeSession(connection)
    with pytest.raises(ValueError, match="not available in your own browser"):
        await session.execute(BrowserCommand(command="new_tab", arguments=[]))
