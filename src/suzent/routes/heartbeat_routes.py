"""
Heartbeat system API routes.
"""

import json
from typing import Optional
from datetime import datetime
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.config import CONFIG
from suzent.core.heartbeat import HeartbeatRunner, get_active_heartbeat
from suzent.database import get_database


# Path to the global heartbeat settings file
_HEARTBEAT_CONFIG_PATH = Path(CONFIG.sandbox_data_path) / "config" / "heartbeat.json"


def _load_heartbeat_config() -> dict:
    try:
        if _HEARTBEAT_CONFIG_PATH.exists():
            return json.loads(_HEARTBEAT_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_heartbeat_config(cfg: dict) -> None:
    _HEARTBEAT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HEARTBEAT_CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _get_runner() -> Optional[HeartbeatRunner]:
    """Return the active HeartbeatRunner, or None."""
    return get_active_heartbeat()


def _not_initialized() -> JSONResponse:
    return JSONResponse({"error": "HeartbeatRunner not initialized"}, status_code=503)


def _update_chat_config(chat_id: str, updates: dict) -> bool:
    """Update specific keys in a chat's config within a single session. Returns True on success."""
    from sqlmodel import Session
    from sqlalchemy.orm.attributes import flag_modified
    from suzent.database import ChatModel

    db = get_database()
    with Session(db.engine) as session:
        chat = session.get(ChatModel, chat_id)
        if not chat:
            return False
        for key, value in updates.items():
            if value is None:
                chat.config.pop(key, None)
            else:
                chat.config[key] = value
        chat.updated_at = datetime.now()
        flag_modified(chat, "config")
        session.commit()
    return True


async def get_heartbeat_status(request: Request) -> JSONResponse:
    """Get heartbeat system status."""
    chat_id = request.query_params.get("chat_id")
    if not (runner := _get_runner()):
        return JSONResponse({"enabled": False, "running": False})
    return JSONResponse(runner.get_status(chat_id))


async def enable_heartbeat(request: Request) -> JSONResponse:
    """Enable the heartbeat system for a chat."""
    body = await request.json()
    chat_id = body.get("chat_id")
    if chat_id:
        ok = _update_chat_config(chat_id, {"heartbeat_enabled": True})
        if not ok:
            return JSONResponse({"error": "Chat not found"}, status_code=404)

    # Always ensure the global runner is spinning
    if runner := _get_runner():
        await runner.enable()

    return JSONResponse({"success": True})


async def disable_heartbeat(request: Request) -> JSONResponse:
    """Disable the heartbeat system for a chat."""
    body = await request.json()
    chat_id = body.get("chat_id")
    if chat_id:
        ok = _update_chat_config(chat_id, {"heartbeat_enabled": False})
        if not ok:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        return JSONResponse({"success": True})
    else:
        # No chat_id — disable global runner
        if runner := _get_runner():
            await runner.disable()
        return JSONResponse({"success": True})


async def trigger_heartbeat(request: Request) -> JSONResponse:
    """Trigger an immediate heartbeat tick."""
    body = await request.json()
    chat_id = body.get("chat_id")
    if not (runner := _get_runner()):
        return _not_initialized()
    if chat_id:
        await runner.trigger_now(chat_id)
    return JSONResponse({"success": True})


async def get_heartbeat_md(request: Request) -> JSONResponse:
    """Get heartbeat instructions for a chat."""
    chat_id = request.query_params.get("chat_id")
    if chat_id:
        hb_path = Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
        if hb_path.exists():
            try:
                content = hb_path.read_text(encoding="utf-8")
                return JSONResponse({"content": content, "exists": True})
            except Exception:
                pass
    return JSONResponse({"content": "", "exists": False})


async def save_heartbeat_md(request: Request) -> JSONResponse:
    """Write the heartbeat instructions for a chat."""
    body = await request.json()
    chat_id = body.get("chat_id")
    content = body.get("content", "")

    if not chat_id:
        return JSONResponse({"error": "chat_id required"}, status_code=400)

    hb_path = Path(CONFIG.sandbox_data_path) / "sessions" / chat_id / "heartbeat.md"
    try:
        hb_path.parent.mkdir(parents=True, exist_ok=True)
        hb_path.write_text(content, encoding="utf-8")

        # Ensure heartbeat_instructions is removed from DB config (file is source of truth)
        _update_chat_config(chat_id, {"heartbeat_instructions": None})

        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def set_heartbeat_interval(request: Request) -> JSONResponse:
    """Set the heartbeat interval in minutes for a chat."""
    body = await request.json()
    chat_id = body.get("chat_id")
    minutes = body.get("interval_minutes")

    if not isinstance(minutes, int) or minutes < 1:
        return JSONResponse(
            {"error": "interval_minutes must be a positive integer"},
            status_code=400,
        )

    if not chat_id:
        return JSONResponse({"error": "chat_id required"}, status_code=400)

    ok = _update_chat_config(chat_id, {"heartbeat_interval_minutes": minutes})
    if not ok:
        return JSONResponse({"error": "Chat not found"}, status_code=404)
    return JSONResponse({"success": True, "interval_minutes": minutes})


async def get_heartbeat_global_config(request: Request) -> JSONResponse:
    """Get global heartbeat settings (e.g. allowed tools)."""
    return JSONResponse(_load_heartbeat_config())


async def save_heartbeat_global_config(request: Request) -> JSONResponse:
    """Save global heartbeat settings."""
    try:
        data = await request.json()
        cfg = _load_heartbeat_config()
        cfg.update(data)
        _save_heartbeat_config(cfg)
        return JSONResponse({"success": True})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
