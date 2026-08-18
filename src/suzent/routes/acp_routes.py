"""REST endpoints for local ACP agents and sessions."""

from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.acp import get_acp_manager
from suzent.database import get_database


async def list_acp_agents(_request: Request) -> JSONResponse:
    manager = get_acp_manager()
    return JSONResponse(
        {"agents": [agent.diagnostics() for agent in manager.registry.list_agents()]}
    )


async def list_acp_sessions(_request: Request) -> JSONResponse:
    db = get_database()
    sessions = []
    for summary in db.list_chats(limit=1000):
        chat = db.get_chat(summary.id)
        config = dict(chat.config or {}) if chat else {}
        if config.get("runtime") != "acp":
            continue
        sessions.append(
            {
                "chat_id": summary.id,
                "title": summary.title,
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

        managed = await manager.create(
            chat_id="probe", agent_id=agent_id, cwd=agent.cwd or str(Path.cwd())
        )
        try:
            init_result = await managed.client.initialize()
            capabilities = (
                init_result.capabilities.model_dump()
                if init_result.capabilities
                else {}
            )
            server_info = (
                init_result.serverInfo.model_dump() if init_result.serverInfo else {}
            )
            protocol_version = init_result.protocolVersion
        finally:
            await manager.stop(managed.session_id)

        return JSONResponse(
            {
                "protocolVersion": protocol_version,
                "agentInfo": server_info,
                "capabilities": capabilities,
            }
        )
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
