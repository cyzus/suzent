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

    # Accept connection immediately
    await session_mgr.add_client(websocket)

    try:
        while True:
            data = await websocket.receive_json()
            await session_mgr.handle_client_message(data)
    except Exception as e:
        logger.debug(f"WebSocket client disconnected: {e}")
    finally:
        await session_mgr.remove_client(websocket)
