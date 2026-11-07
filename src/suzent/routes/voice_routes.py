"""Realtime voice and wake-word routes."""

from __future__ import annotations

import asyncio
import uuid

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.auth_boundary import voice_origin_allowed
from suzent.database import get_database
from suzent.voice.realtime import VoiceBridge


async def voice_websocket_endpoint(websocket: WebSocket) -> None:
    if not voice_origin_allowed(
        websocket.headers.get("origin"), websocket.headers.get("host", "")
    ):
        await websocket.close(code=1008)
        return

    db = get_database()
    requested_chat_id = (websocket.query_params.get("chat_id") or "").strip()
    chat_id = (
        requested_chat_id
        if requested_chat_id and db.get_chat(requested_chat_id)
        else uuid.uuid4().hex
    )
    if db.get_chat(chat_id) is None:
        from suzent.permissions.context import seed_default_permission_mode

        config: dict = {}
        seed_default_permission_mode(config)
        # An unknown project falls back to the default one, as plain chats do.
        project_id = (websocket.query_params.get("project_id") or "").strip()
        if project_id and db.get_project(project_id) is None:
            project_id = ""
        db.create_chat(
            title="Voice conversation",
            config=config,
            chat_id=chat_id,
            project_id=project_id or None,
        )

    await websocket.accept()
    bridge_factory = getattr(websocket.app.state, "voice_bridge_factory", VoiceBridge)
    bridge = bridge_factory(websocket, chat_id)
    await bridge.run()


async def wake_status(request: Request) -> JSONResponse:
    from suzent.voice import wake
    from suzent.voice.settings import get_voice_settings

    phrases = get_voice_settings().wake_phrases
    return JSONResponse(await asyncio.to_thread(wake.status, phrases))


async def wake_install_model(request: Request) -> JSONResponse:
    from suzent.voice import wake

    try:
        await asyncio.to_thread(wake.install_model)
    except wake.WakeUnavailable as exc:
        return JSONResponse({"error": exc.code, "detail": str(exc)}, status_code=502)
    return await wake_status(request)


async def wake_websocket_endpoint(websocket: WebSocket) -> None:
    """Spot the wake phrase in the app's mic audio; say so when it is heard.

    The app sends 16 kHz mono int16 PCM as binary frames and gets ``ready``,
    then ``wake`` each time a phrase is heard, or one ``error`` and a close.
    """
    from suzent.voice import wake
    from suzent.voice.settings import get_voice_settings

    if not voice_origin_allowed(
        websocket.headers.get("origin"), websocket.headers.get("host", "")
    ):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    settings = get_voice_settings()
    factory = getattr(websocket.app.state, "wake_spotter_factory", wake.WakeSpotter)
    try:
        spotter = await asyncio.to_thread(
            factory,
            wake.SpotterConfig(tuple(settings.wake_phrases), settings.wake_sensitivity),
        )
    except wake.WakeUnavailable as exc:
        await websocket.send_json(
            {"type": "error", "code": exc.code, "detail": str(exc)}
        )
        await websocket.close()
        return
    await websocket.send_json({"type": "ready", "sample_rate": wake.SAMPLE_RATE})
    try:
        while True:
            pcm = await websocket.receive_bytes()
            heard = await asyncio.to_thread(spotter.accept, pcm)
            if heard:
                await websocket.send_json({"type": "wake", "phrase": heard})
    except (WebSocketDisconnect, KeyError):
        # KeyError: a text frame where audio was expected ends the session too.
        return
