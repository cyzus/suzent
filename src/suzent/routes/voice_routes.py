"""Realtime voice WebSocket route."""

from __future__ import annotations

import uuid

from starlette.websockets import WebSocket

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
        db.create_chat(title="Voice conversation", config={}, chat_id=chat_id)

    await websocket.accept()
    bridge_factory = getattr(websocket.app.state, "voice_bridge_factory", VoiceBridge)
    bridge = bridge_factory(websocket, chat_id)
    await bridge.run()
