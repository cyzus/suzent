import asyncio
import json
import os

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket
from suzent.logger import get_logger
from suzent.tools.browser.config import BrowserPreferences, BrowserSettings
from suzent.tools.browser.detection import available_browsers
from suzent.tools.browser.tool import BrowserSessionManager
from suzent.tools.browser.extension.session import session as extension_session
from suzent.tools.browser.extension.bridge import bridge
from suzent.tools.browser.extension.routes import local_setup_request

logger = get_logger(__name__)


async def browser_status_endpoint(request: Request) -> JSONResponse:
    if not local_setup_request(request) or (
        request.method == "POST"
        and request.headers.get("x-suzent-browser-setup") != "1"
    ):
        return JSONResponse({"error": "Use the local Suzent app"}, status_code=403)
    settings = await asyncio.to_thread(BrowserSettings.load)
    manager = BrowserSessionManager.get_instance()
    result = {
        "mode": settings.connection_mode,
        "browser": settings.channel,
        "connected": False,
        "selected": False,
        "title": None,
    }
    try:
        if settings.connection_mode == "extension":
            result["connected"] = bridge.socket is not None
            if bridge.socket:
                result.update(await bridge.request("status"))
            if request.method == "POST":
                await bridge.request("focus")
        else:
            async with manager._action_lock:
                page = manager._page
                if (
                    manager.settings.connection_mode == settings.connection_mode
                    and page
                    and not page.is_closed()
                ):
                    result.update(
                        connected=True, selected=True, title=await page.title()
                    )
                    if request.method == "POST":
                        await page.bring_to_front()
                elif request.method == "POST":
                    raise ValueError("No browser tab is selected")
        return JSONResponse(result)
    except Exception:
        return JSONResponse({"error": "Browser tab unavailable"}, status_code=409)


async def browser_settings_endpoint(request: Request) -> JSONResponse:
    try:
        if request.method == "POST":
            if (
                not local_setup_request(request)
                or request.headers.get("x-suzent-browser-setup") != "1"
            ):
                return JSONResponse(
                    {"error": "Use the local Suzent app"}, status_code=403
                )
            preferences = BrowserPreferences.model_validate(await request.json())
            if "connection_mode" in preferences.model_fields_set:
                manager = BrowserSessionManager.get_instance()
                async with manager._action_lock:
                    await asyncio.to_thread(preferences.save_changes)
                    effective = await asyncio.to_thread(BrowserSettings.load)
                    if effective.connection_mode != "extension":
                        await extension_session.close()
                    if (
                        manager._playwright
                        and manager.settings.connection_mode
                        != effective.connection_mode
                    ):
                        await manager.close_session()
            else:
                await asyncio.to_thread(preferences.save_changes)
        settings = await asyncio.to_thread(BrowserSettings.load)
        return JSONResponse(
            {
                "settings": settings.model_dump(
                    include=set(BrowserPreferences.model_fields)
                ),
                "environment_overrides": [
                    field
                    for field in BrowserPreferences.model_fields
                    if f"SUZENT_BROWSER_{field.upper()}" in os.environ
                ],
                "available_browsers": await asyncio.to_thread(available_browsers),
            }
        )
    except (ValidationError, json.JSONDecodeError):
        return JSONResponse({"error": "Invalid browser settings"}, status_code=400)
    except OSError:
        logger.warning("Could not read or save browser settings")
        return JSONResponse(
            {"error": "Could not read or save browser settings"}, status_code=500
        )


async def browser_websocket_endpoint(websocket: WebSocket):
    # Browser WebSocket requests bypass CORS; loopback alone is not a UI identity.
    if not local_setup_request(websocket):
        await websocket.close(code=1008)
        return
    session_mgr = BrowserSessionManager.get_instance()

    if BrowserSettings.load().connection_mode == "extension":
        async with session_mgr._action_lock:
            if session_mgr._playwright:
                await session_mgr.close_session()
    # Accept connection immediately
    await session_mgr.add_client(websocket)
    extension_session.clients.append(websocket)
    try:
        if BrowserSettings.load().connection_mode == "extension":
            await extension_session.start_streaming()
        while True:
            data = await websocket.receive_json()
            try:
                if BrowserSettings.load().connection_mode == "extension":
                    async with session_mgr._action_lock:
                        if session_mgr._playwright:
                            await session_mgr.close_session()
                        await extension_session.handle_preview(data)
                else:
                    if extension_session.selected:
                        await extension_session.close()
                    await session_mgr.handle_client_message(data)
            except ValueError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
    except Exception as e:
        logger.debug(f"WebSocket client disconnected: {e}")
    finally:
        await session_mgr.remove_client(websocket)
        await extension_session.remove_client(websocket)
