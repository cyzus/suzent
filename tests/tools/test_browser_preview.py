import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from suzent.routes import browser_routes
from suzent.tools.browser.config import BrowserSettings
from suzent.tools.browser.preview import PreviewFrames


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
        result = await client.get("/browser/status")
        assert result.json()["title"] == "Example"
        assert (await client.post("/browser/status")).status_code == 403
        assert (
            await client.post(
                "/browser/status", headers={"X-Suzent-Browser-Setup": "1"}
            )
        ).status_code == 200
        assert (
            await client.get(
                "/browser/status", headers={"Origin": "https://evil.example"}
            )
        ).status_code == 403
    assert [call.args[0] for call in request.call_args_list] == [
        "status",
        "status",
        "focus",
    ]
