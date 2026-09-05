import asyncio
from pathlib import Path

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from suzent.routes.browser_routes import browser_settings_endpoint
from suzent.routes import browser_routes
from suzent.tools import browser_config
from suzent.tools.browsing_tool import BrowserSessionManager


@pytest.fixture
def settings_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(browser_config, "USER_CONFIG_DIR", tmp_path)
    for field in browser_config.BrowserSettings.model_fields:
        monkeypatch.delenv(f"SUZENT_BROWSER_{field.upper()}", raising=False)
    return tmp_path / "browser.json"


def make_client() -> httpx.AsyncClient:
    app = Starlette(
        routes=[
            Route(
                "/browser/settings", browser_settings_endpoint, methods=["GET", "POST"]
            )
        ]
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    )


async def test_settings_roundtrip_and_manager_startup(settings_path: Path) -> None:
    async with make_client() as client:
        initial = await client.get("/browser/settings")
        assert initial.json()["settings"] == {
            "persistent": False,
            "headless": True,
            "channel": "chromium",
        }
        values = {"persistent": True, "headless": False, "channel": "msedge"}
        saved = await client.post("/browser/settings", json=values)
        assert saved.status_code == 200
        assert saved.json()["settings"] == values
        assert settings_path.exists()
        loaded = await client.get("/browser/settings")
        assert loaded.json()["settings"] == values
    manager = BrowserSessionManager()
    assert manager.settings.persistent
    assert not manager.settings.headless
    assert manager.settings.channel == "msedge"
    assert manager._browser is None


@pytest.mark.parametrize(
    "values",
    [
        {"channel": "firefox"},
        {"persistent": "true"},
        {"headless": 1},
        {"profile_dir": "C:/Users/example"},
        None,
    ],
)
async def test_invalid_settings_preserve_saved_file(
    settings_path: Path, values: object
) -> None:
    browser_config.BrowserPreferences(persistent=True).save()
    original = settings_path.read_text()
    async with make_client() as client:
        result = await client.post("/browser/settings", json=values)
        assert result.status_code == 400
    assert settings_path.read_text() == original


async def test_environment_overrides_are_reported(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUZENT_BROWSER_CHANNEL", "chrome")
    async with make_client() as client:
        result = await client.post(
            "/browser/settings",
            json={"persistent": True, "headless": False, "channel": "msedge"},
        )
        assert result.json()["settings"]["channel"] == "chrome"
        assert result.json()["environment_overrides"] == ["channel"]
    monkeypatch.delenv("SUZENT_BROWSER_CHANNEL")
    assert browser_config.BrowserSettings.load().channel == "msedge"


async def test_save_does_not_interrupt_active_manager(settings_path: Path) -> None:
    manager = BrowserSessionManager()
    async with make_client() as client:
        assert (
            await client.post("/browser/settings", json={"persistent": True})
        ).status_code == 200
    assert not manager.settings.persistent
    assert BrowserSessionManager().settings.persistent


async def test_settings_reports_installed_browsers_without_changing_selection(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    browser_config.BrowserPreferences(channel="msedge").save()
    availability = {"chromium": True, "chrome": True, "msedge": False}
    monkeypatch.setattr(browser_routes, "available_browsers", lambda: availability)
    async with make_client() as client:
        result = await client.get("/browser/settings")
        assert result.json()["available_browsers"] == availability
        assert result.json()["settings"]["channel"] == "msedge"
        availability["msedge"] = True
        refreshed = await client.get("/browser/settings")
        assert refreshed.json()["available_browsers"]["msedge"]


async def test_hot_reload_waits_for_action_and_restarts_only_browser(
    settings_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "SUZENT_BROWSER_PROFILE_DIR", str(settings_path.parent / "profile")
    )
    manager = BrowserSessionManager()
    try:
        assert not await manager.ensure_session()
        original_browser = manager._browser
        original_page = manager._page
        await original_page.set_content("<button>Old page</button>")
        await manager.get_snapshot()
        ref = next(iter(manager._selector_map))
        async with manager._action_lock:
            async with make_client() as client:
                result = await client.post(
                    "/browser/settings", json={"persistent": True}
                )
                assert result.status_code == 200
            restart = asyncio.create_task(manager.ensure_session())
            await asyncio.sleep(0)
            assert not restart.done()
            assert not original_page.is_closed()
        assert await restart
        assert original_page.is_closed()
        assert manager._browser is not original_browser
        assert manager.settings.persistent
        assert not (await manager.interact("click", ref)).success
        current_browser = manager._browser
        assert not await manager.ensure_session()
        assert manager._browser is current_browser
    finally:
        await manager.close_session()
