from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import Error, TimeoutError as PlaywrightTimeoutError

from suzent.tools.base import ToolErrorCode
from suzent.tools.browser.config import BrowserSettings, normalize_browser_url
from suzent.tools.browser.tool import BrowserSessionManager, BrowsingTool


@pytest.mark.parametrize(
    "command,args",
    [
        ("click", ["click", "@g1e0"]),
        ("click", ["button"]),
        ("fill", ["@g1e0"]),
        ("press", ["@g1e0", ""]),
        ("click_coords", ["x", "2"]),
        ("click_coords", ["-1", "2"]),
        ("scroll", ["1"]),
        ("back", ["unexpected"]),
        ("snapshot", ["0", "101"]),
        ("snapshot", ["-1"]),
        ("open", ["javascript:alert(1)"]),
        ("open", ["file:///tmp/test"]),
        ("open", ["https://user:secret@example.com"]),
        ("bogus", []),
    ],
)
async def test_invalid_arguments_do_not_launch_browser(
    command: str, args: list[str]
) -> None:
    tool = BrowsingTool()
    tool.session_mgr = AsyncMock()
    tool.session_mgr.ensure_session.return_value = False
    result = await tool._execute(command, args)
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    tool.session_mgr.ensure_session.assert_not_awaited()
    assert "secret" not in result.message


async def test_scroll_honors_arguments_and_empty_open() -> None:
    tool = BrowsingTool()
    tool.session_mgr = AsyncMock()
    tool.session_mgr.ensure_session.return_value = False
    assert (await tool._execute("scroll", ["12", "-300"])).success
    tool.session_mgr.scroll.assert_awaited_once_with(12, -300)
    assert (await tool._execute("open", [])).success
    tool.session_mgr.goto.assert_awaited_once_with("about:blank")


async def test_navigation_timeout_is_structured() -> None:
    tool = BrowsingTool()
    tool.session_mgr = AsyncMock()
    tool.session_mgr.ensure_session.return_value = False
    tool.session_mgr.reload.side_effect = PlaywrightTimeoutError("timeout")
    assert (await tool._execute("reload")).error_code == ToolErrorCode.TIMEOUT


async def test_settings_restart_does_not_replay_old_coordinates() -> None:
    tool = BrowsingTool()
    tool.session_mgr = AsyncMock()
    tool.session_mgr.ensure_session.return_value = True
    result = await tool._execute("click_coords", ["10", "20"])
    assert not result.success and "restarted" in result.message
    tool.session_mgr.click.assert_not_awaited()


def test_url_normalization() -> None:
    assert normalize_browser_url("example.com") == "https://example.com"
    assert normalize_browser_url("localhost:8000/path") == "https://localhost:8000/path"


def test_browser_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SUZENT_BROWSER_PERSISTENT", "true")
    monkeypatch.setenv("SUZENT_BROWSER_HEADLESS", "false")
    monkeypatch.setenv("SUZENT_BROWSER_CHANNEL", "msedge")
    monkeypatch.setenv("SUZENT_BROWSER_PROFILE_DIR", str(tmp_path))
    settings = BrowserSettings.from_environment()
    assert settings.persistent and not settings.headless
    assert settings.channel == "msedge"
    assert settings.profile_dir == tmp_path


@pytest.fixture
async def browser() -> AsyncIterator[BrowserSessionManager]:
    manager = BrowserSessionManager(BrowserSettings())
    try:
        await manager.ensure_session()
    except Error as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip(
                "Run uv run playwright install chromium for browser regression tests"
            )
        raise
    try:
        yield manager
    finally:
        await manager.close_session()


async def test_snapshot_budget_pagination_and_secrets(
    browser: BrowserSessionManager,
) -> None:
    await browser._page.set_content(
        "<title>Fixture</title><p>Readable article text</p>"
        "<input type=password value='never-echo-this'>"
        "<textarea>private-draft</textarea>"
        + "".join(f"<button>Item {i}</button>" for i in range(110))
    )
    first = await browser.get_snapshot()
    assert first.success, first.message
    assert first.metadata["element_count"] == 80
    assert first.metadata["total"] == 112
    assert first.metadata["next_offset"] == 80
    assert "Fixture" in first.message and "Readable article text" in first.message
    assert (
        "never-echo-this" not in first.message and "private-draft" not in first.message
    )
    old_ref = next(iter(browser._selector_map))
    second = await browser.get_snapshot(offset=80)
    assert second.success and second.metadata["element_count"] == 32
    assert not (await browser.interact("click", old_ref)).success


async def test_snapshot_distinguishes_unlabeled_controls(
    browser: BrowserSessionManager,
) -> None:
    await browser._page.set_content("""
        <a href="/account?token=private-token#private-fragment"><svg width="20" height="20"></svg></a>
        <a href="https://user:private-password@example.com/settings"><svg width="20" height="20"></svg></a>
        <input type="email" name="account_email" value="private-email">
        <input type="password" name="account_password" value="private-secret">
    """)
    result = await browser.get_snapshot(interactive_only=True)
    assert result.success, result.message
    assert 'href="/account"' in result.message
    assert 'href="https://example.com/settings"' in result.message
    assert 'type="email" name="account_email"' in result.message
    assert 'type="password" name="account_password"' in result.message
    assert "private-" not in result.message


async def test_detached_node_is_not_retargeted(browser: BrowserSessionManager) -> None:
    await browser._page.set_content(
        "<button onclick='window.clicked=true'>Save</button>"
    )
    assert (await browser.get_snapshot()).success
    ref = next(iter(browser._selector_map))
    await browser._page.evaluate(
        "document.querySelector('button').outerHTML = '<button onclick=\"window.clicked=true\">Save</button>'"
    )
    assert not (await browser.interact("click", ref)).success
    assert await browser._page.evaluate("window.clicked") is None


async def test_changed_link_is_rejected(browser: BrowserSessionManager) -> None:
    await browser._page.set_content("<a href='/first'>Continue</a>")
    await browser.get_snapshot()
    ref = next(iter(browser._selector_map))
    await browser._page.evaluate("document.querySelector('a').href='/second'")
    assert not (await browser.interact("click", ref)).success


async def test_fill_does_not_echo_values(browser: BrowserSessionManager) -> None:
    await browser._page.set_content("<input type=password aria-label=Password>")
    await browser.get_snapshot()
    ref = next(iter(browser._selector_map))
    result = await browser.interact("fill", ref, "sensitive-value")
    assert result.success, result.message
    assert await browser._page.locator("input").input_value() == "sensitive-value"
    assert "sensitive-value" not in result.model_dump_json()
    assert "sensitive-value" not in (await browser.get_snapshot()).message


async def test_reload_and_navigation_expire_refs(
    browser: BrowserSessionManager,
) -> None:
    await browser._context.route(
        "https://browser.test/**",
        lambda route: route.fulfill(
            content_type="text/html",
            body="<title>Reload fixture</title><button>Ready</button>",
        ),
    )
    await browser.goto("https://browser.test/")
    await browser.get_snapshot()
    ref = next(iter(browser._selector_map))
    await browser.reload()
    assert not (await browser.interact("click", ref)).success
    fresh = await browser.get_snapshot()
    assert fresh.success and fresh.metadata["element_count"] == 1
    assert fresh.metadata["url"] == "https://browser.test/"


async def test_default_dialog_does_not_block(browser: BrowserSessionManager) -> None:
    await browser._page.set_content("<button onclick=\"alert('hello')\">Alert</button>")
    await browser.get_snapshot()
    assert (await browser.interact("click", next(iter(browser._selector_map)))).success


async def test_delayed_controls_and_empty_page(browser: BrowserSessionManager) -> None:
    await browser._page.set_content(
        "<script>setTimeout(() => document.body.innerHTML = '<button>Hydrated</button>', 150)</script>"
    )
    result = await browser.get_snapshot()
    assert result.success and result.metadata["element_count"] == 1
    assert "Hydrated" in result.message
    await browser._page.set_content("<title>No controls</title><p>Article only</p>")
    result = await browser.get_snapshot()
    assert result.success and result.metadata["element_count"] == 0
    assert "No controls" in result.message and "Article only" in result.message


async def test_persistent_profile_retains_cookies(
    browser: BrowserSessionManager, tmp_path: Path
) -> None:
    # The browser fixture verifies Chromium is installed before launching profiles.
    settings = BrowserSettings(persistent=True, profile_dir=tmp_path / "profile")
    first = BrowserSessionManager(settings)
    try:
        await first.ensure_session()
        await first._context.add_cookies(
            [
                {
                    "name": "session-test",
                    "value": "remembered",
                    "domain": "browser.test",
                    "path": "/",
                    "expires": 2000000000,
                }
            ]
        )
    finally:
        await first.close_session()
    second = BrowserSessionManager(settings)
    try:
        await second.ensure_session()
        cookies = await second._context.cookies("https://browser.test/")
        assert any(
            cookie["name"] == "session-test" and cookie["value"] == "remembered"
            for cookie in cookies
        )
    finally:
        await second.close_session()
