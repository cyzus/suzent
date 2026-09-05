from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from suzent.tools import browser_connection
from suzent.tools.browser_config import BrowserCommand, BrowserSettings
from suzent.tools.browsing_tool import BrowserSessionManager


@pytest.mark.parametrize("channel", ["chrome", "msedge"])
def test_discovery_reads_only_local_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, channel: str
) -> None:
    monkeypatch.setattr(browser_connection, "browser_user_data_dir", lambda _: tmp_path)
    (tmp_path / "DevToolsActivePort").write_text("12345\n/devtools/browser/abc-123\n")
    assert browser_connection.discover_browser_endpoint(channel) == (
        "ws://127.0.0.1:12345/devtools/browser/abc-123"
    )


@pytest.mark.parametrize(
    "contents",
    [
        "",
        "0\n/devtools/browser/abc",
        "65536\n/devtools/browser/abc",
        "9222\nws://remote.example/path",
        "9222\n/devtools/browser/abc?secret=x",
    ],
)
def test_invalid_discovery_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, contents: str
) -> None:
    monkeypatch.setattr(browser_connection, "browser_user_data_dir", lambda _: tmp_path)
    (tmp_path / "DevToolsActivePort").write_text(contents)
    with pytest.raises(ValueError, match="enable remote debugging"):
        browser_connection.discover_browser_endpoint("msedge")


def test_select_tab_requires_stable_id() -> None:
    with pytest.raises(ValueError):
        BrowserCommand(command="select_tab", arguments=["0"])
    assert BrowserCommand(command="select_tab", arguments=["tab-1"])


async def test_failed_attachment_never_closes_external_browser() -> None:
    manager = BrowserSessionManager(BrowserSettings(connection_mode="existing"))
    manager._attached = True
    context, browser, playwright = AsyncMock(), AsyncMock(), AsyncMock()
    manager._context, manager._browser, manager._playwright = (
        context,
        browser,
        playwright,
    )
    await manager.close_session()
    context.close.assert_not_awaited()
    browser.close.assert_not_awaited()
    playwright.stop.assert_awaited_once()


@pytest.mark.parametrize("channel", ["chromium", "chrome", "msedge"])
async def test_attach_tabs_actions_and_disconnect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, channel: str
) -> None:
    from suzent.tools.browser_detection import available_browsers

    if not available_browsers()[channel]:
        pytest.skip(f"{channel} is not installed")
    # This browser belongs to the test, never to the user's personal profile.
    async with async_playwright() as owner:
        context = await owner.chromium.launch_persistent_context(
            str(tmp_path),
            headless=True,
            channel=None if channel == "chromium" else channel,
            args=["--remote-debugging-port=0"],
        )
        original = context.pages[0]
        await original.set_content(
            "<button onclick=\"this.textContent='Done'\">Test</button>"
        )
        monkeypatch.setattr(
            browser_connection, "browser_user_data_dir", lambda _: tmp_path
        )
        manager = BrowserSessionManager(
            BrowserSettings(connection_mode="existing", channel="msedge")
        )
        try:
            await manager.ensure_session()
            await original.title()
            assert len(context.pages) == 2
            assert manager._page.url == "about:blank"
            result = await manager.tabs()
            tab_id = result.metadata["tabs"][0]["id"]
            assert (await manager.select_tab(tab_id)).success
            assert (await manager.get_snapshot()).success
            ref = next(iter(manager._selector_map))
            assert (await manager.interact("click", ref)).success
            assert await original.locator("button").inner_text() == "Done"
            await manager.select_tab(result.metadata["tabs"][1]["id"])
            assert not (await manager.interact("click", ref)).success
            await manager._page.close()
            assert await manager.ensure_session()
            assert not (await manager.select_tab(tab_id)).success
            assert not (await manager.interact("click", ref)).success
            await manager.close_session()
            assert not original.is_closed()
            assert await original.locator("button").inner_text() == "Done"
            assert len(context.pages) == 2
        finally:
            await manager.close_session()
            await context.close()
