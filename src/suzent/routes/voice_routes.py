"""Realtime voice route."""

from __future__ import annotations

import asyncio
import uuid

from starlette.websockets import WebSocket

from suzent.auth_boundary import voice_origin_allowed
from suzent.database import get_database
from suzent.logger import get_logger
from suzent.voice.realtime import VoiceBridge

logger = get_logger(__name__)


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
    created = db.get_chat(chat_id) is None
    if created:
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
    if created and not bridge.router.delegated:
        await asyncio.to_thread(_discard_if_empty, chat_id)


def _discard_if_empty(chat_id: str) -> None:
    """Drop the chat a call created when nothing was ever sent to Suzent.

    A call that only chatted with the front desk leaves no messages, and an
    empty "Voice conversation" in the chat list is just clutter.
    """
    from suzent.core.stream_registry import is_background_streaming

    db = get_database()
    chat = db.get_chat(chat_id)
    if chat is None or chat.messages or is_background_streaming(chat_id):
        return
    db.delete_chat(chat_id)
    logger.debug("Voice call {} sent nothing to Suzent; empty chat removed", chat_id)
