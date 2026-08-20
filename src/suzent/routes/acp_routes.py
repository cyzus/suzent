"""REST endpoints for local ACP agents and sessions."""

from __future__ import annotations

import uuid
from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.acp import get_acp_manager
from suzent.acp.permissions import get_permission_broker
from suzent.database import get_database


async def list_acp_agents(_request: Request) -> JSONResponse:
    manager = get_acp_manager()
    return JSONResponse(
        {"agents": [agent.diagnostics() for agent in manager.registry.list_agents()]}
    )


async def list_acp_sessions(_request: Request) -> JSONResponse:
    db = get_database()
    sessions = []
    for row in db.list_chats_by_config("runtime", "acp"):
        config = row["config"]
        sessions.append(
            {
                "chat_id": row["id"],
                "title": row["title"],
                "agent_id": config.get("acp_agent_id"),
                "session_id": config.get("acp_session_id"),
                "cwd": config.get("acp_cwd") or config.get("cwd"),
                "platform": config.get("platform"),
            }
        )
    return JSONResponse(
        {"sessions": sessions, "active": get_acp_manager().list_active()}
    )


async def create_acp_session(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        agent_id = str(data.get("agent_id") or data.get("agentId") or "").strip()
        if not agent_id:
            return JSONResponse({"error": "agent_id is required"}, status_code=400)
        cwd = str(data.get("cwd") or Path.cwd())
        config = dict(data.get("config") or {})
        config.update({"runtime": "acp", "acp_agent_id": agent_id, "acp_cwd": cwd})
        db = get_database()
        chat_id = db.create_chat(
            str(data.get("title") or "ACP Session"),
            config,
            project_id=data.get("project_id") or data.get("projectId"),
        )
        try:
            managed = await get_acp_manager().create(chat_id, agent_id, cwd)
        except Exception:
            db.delete_chat(chat_id)
            raise
        db.merge_chat_config(chat_id, {"acp_session_id": managed.session_id})
        return JSONResponse(
            {
                "chat_id": chat_id,
                "agent_id": agent_id,
                "session_id": managed.session_id,
                "cwd": cwd,
            },
            status_code=201,
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def probe_acp_agent(request: Request) -> JSONResponse:
    try:
        agent_id = request.path_params.get("agent_id")
        if not agent_id:
            return JSONResponse({"error": "agent_id is required"}, status_code=400)

        manager = get_acp_manager()
        try:
            agent = manager.registry.get(agent_id)
        except KeyError:
            return JSONResponse({"error": "Agent not found"}, status_code=404)

        if not agent.available:
            return JSONResponse(
                {"error": "Agent binary not found or unavailable"}, status_code=400
            )

        # Unique key so concurrent probes don't evict each other's subprocess.
        probe_chat_id = f"probe:{agent_id}:{uuid.uuid4().hex}"
        managed = await manager.create(
            chat_id=probe_chat_id, agent_id=agent_id, cwd=agent.cwd or str(Path.cwd())
        )
        try:
            # The handshake already ran during create(); report what it returned.
            return JSONResponse(
                {
                    "protocolVersion": managed.protocol_version,
                    "agentInfo": managed.agent_info,
                    "capabilities": managed.capabilities,
                }
            )
        finally:
            await manager.stop(probe_chat_id)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def resume_acp_session(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        chat_id = str(data.get("chat_id") or data.get("chatId") or "").strip()
        session_id = str(data.get("session_id") or data.get("sessionId") or "").strip()
        if not chat_id or not session_id:
            return JSONResponse(
                {"error": "chat_id and session_id are required"}, status_code=400
            )
        db = get_database()
        chat = db.get_chat(chat_id)
        if chat is None:
            return JSONResponse({"error": "Chat not found"}, status_code=404)
        config = dict(chat.config or {})
        agent_id = str(
            data.get("agent_id")
            or data.get("agentId")
            or config.get("acp_agent_id")
            or ""
        ).strip()
        if not agent_id:
            return JSONResponse({"error": "agent_id is required"}, status_code=400)
        cwd = str(
            data.get("cwd") or config.get("acp_cwd") or config.get("cwd") or Path.cwd()
        )
        managed = await get_acp_manager().resume(chat_id, agent_id, session_id, cwd)
        db.merge_chat_config(
            chat_id,
            {
                "runtime": "acp",
                "acp_agent_id": agent_id,
                "acp_session_id": managed.session_id,
                "acp_cwd": cwd,
            },
        )
        return JSONResponse(
            {
                "chat_id": chat_id,
                "agent_id": agent_id,
                "session_id": managed.session_id,
                "cwd": cwd,
            }
        )
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


async def list_acp_permissions(request: Request) -> JSONResponse:
    """Pending ACP permission requests, optionally scoped to one chat.

    Readable by the UI and by a Suzent agent deciding on the user's behalf.
    """
    chat_id = request.query_params.get("chat_id") or None
    return JSONResponse({"pending": get_permission_broker().list_pending(chat_id)})


async def resolve_acp_permission(request: Request) -> JSONResponse:
    """Answer one parked ACP permission request.

    Body: ``{"approved": bool, "option_id": "<optional explicit ACP optionId>"}``.
    """
    try:
        request_id = str(request.path_params.get("request_id") or "").strip()
        if not request_id:
            return JSONResponse({"error": "request_id is required"}, status_code=400)
        data = await request.json()
        if "approved" not in data and "outcome" not in data:
            return JSONResponse({"error": "approved is required"}, status_code=400)
        approved = bool(
            data.get("approved")
            if "approved" in data
            else str(data.get("outcome")).lower() in {"allow", "allowed", "selected"}
        )
        option_id = data.get("option_id") or data.get("optionId")
        resolved = get_permission_broker().resolve(
            request_id,
            approved=approved,
            option_id=str(option_id) if option_id else None,
        )
        if not resolved:
            return JSONResponse(
                {"error": "Unknown or already-resolved request"}, status_code=404
            )
        return JSONResponse({"status": "resolved", "approved": approved})
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
