"""Wake-word API, served at /plugins/wake-word/api/<path> and /ws/<path>."""

from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.voice.settings import get_voice_settings

from . import spotter


async def status(request: Request) -> JSONResponse:
    phrases = get_voice_settings().wake_phrases
    return JSONResponse(await asyncio.to_thread(spotter.status, phrases))


async def install_model(request: Request) -> JSONResponse:
    try:
        await asyncio.to_thread(spotter.install_model)
    except spotter.WakeUnavailable as exc:
        return JSONResponse({"error": exc.code, "detail": str(exc)}, status_code=502)
    return await status(request)


async def listen(websocket: WebSocket) -> None:
    """Spot the wake phrase in the app's mic audio; say so when it is heard.

    The app sends 16 kHz mono int16 PCM as binary frames and gets ``ready``,
    then ``wake`` each time a phrase is heard, or one ``error`` and a close.
    """
    await websocket.accept()
    settings = get_voice_settings()
    factory = getattr(websocket.app.state, "wake_spotter_factory", spotter.WakeSpotter)
    try:
        listener = await asyncio.to_thread(
            factory,
            spotter.SpotterConfig(
                tuple(settings.wake_phrases), settings.wake_sensitivity
            ),
        )
    except spotter.WakeUnavailable as exc:
        await websocket.send_json(
            {"type": "error", "code": exc.code, "detail": str(exc)}
        )
        await websocket.close()
        return
    await websocket.send_json({"type": "ready", "sample_rate": spotter.SAMPLE_RATE})
    try:
        while True:
            pcm = await websocket.receive_bytes()
            heard = await asyncio.to_thread(listener.accept, pcm)
            if heard:
                await websocket.send_json({"type": "wake", "phrase": heard})
    except (WebSocketDisconnect, KeyError):
        # KeyError: a text frame where audio was expected ends the session too.
        return
