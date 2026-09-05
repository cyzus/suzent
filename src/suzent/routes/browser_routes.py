import asyncio
import json
import os

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket
from suzent.logger import get_logger
from suzent.tools.browser_config import BrowserPreferences, BrowserSettings
from suzent.tools.browser_detection import available_browsers
from suzent.tools.browsing_tool import BrowserSessionManager
from suzent.browser_extension.session import session as extension_session

logger = get_logger(__name__)


async def browser_settings_endpoint(request: Request) -> JSONResponse:
    try:
        if request.method == "POST":
            preferences = BrowserPreferences.model_validate(await request.json())
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
