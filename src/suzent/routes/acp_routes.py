"""REST endpoints for local ACP agents and sessions."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from suzent.acp import get_acp_manager
from suzent.acp.manager import _resolve_project_dir
from suzent.acp.permissions import get_permission_broker
from suzent.database import get_database


async def list_acp_agents(_request: Request) -> JSONResponse:
    manager = get_acp_manager()
    return JSONResponse(
        {"agents": [agent.diagnostics() for agent in manager.registry.list_agents()]}
    )


async def list_acp_sessions(request: Request) -> JSONResponse:
    # Scope to one agent when asked. Without this every agent reported the same
    # total, so the settings tab showed an identical session count on each card.
    agent_id = (request.query_params.get("agent_id") or "").strip()

    db = get_database()
    sessions = []
    for row in db.list_chats_by_config("runtime", "acp"):
        config = row["config"]
        row_agent = config.get("acp_agent_id")
        if agent_id and row_agent != agent_id:
            continue
        sessions.append(
            {
                "chat_id": row["id"],
                "title": row["title"],
                "agent_id": row_agent,
                "session_id": config.get("acp_session_id"),
                "cwd": config.get("acp_cwd") or config.get("cwd"),
                "platform": config.get("platform"),
            }
        )

    active = get_acp_manager().list_active()
    if agent_id:
        active = [item for item in active if item.get("agent_id") == agent_id]
    return JSONResponse({"sessions": sessions, "active": active})


async def create_acp_session(request: Request) -> JSONResponse:
    try:
        data = await request.json()
        agent_id = str(data.get("agent_id") or data.get("agentId") or "").strip()
        if not agent_id:
            return JSONResponse({"error": "agent_id is required"}, status_code=400)
        explicit_cwd = data.get("cwd")
        db = get_database()

        # Attach to the caller's chat when it names one. The chat picker
        # already created a chat before the first send; minting a second one
        # here left every ACP conversation showing up twice in the sidebar
        # (once as "New Chat", once as "ACP Session").
        chat_id = str(data.get("chat_id") or data.get("chatId") or "").strip()
        created_chat = False
        previous_config: dict[str, Any] | None = None

        # Defer the cwd fallback: we need chat_id to resolve the project dir,
        # and chat_id may not be known until the branch below creates one.
        config = dict(data.get("config") or {})
        config.update({"runtime": "acp", "acp_agent_id": agent_id})
        if chat_id:
            existing = db.get_chat(chat_id)
            if existing is None:
                return JSONResponse({"error": "Chat not found"}, status_code=404)
            # The merge below routes the chat to the agent before we know the
            # agent answers. Snapshot the config so a failed handshake can't
            # strand an existing chat on a runtime that never came up.
            previous_config = dict(existing.config or {})
        else:
            chat_id = db.create_chat(
                str(data.get("title") or "ACP Session"),
                config,
                project_id=data.get("project_id") or data.get("projectId"),
            )
            created_chat = True

        cwd = str(explicit_cwd) if explicit_cwd else _resolve_project_dir(chat_id)
        config["acp_cwd"] = cwd
        if previous_config is not None:
            db.merge_chat_config(chat_id, config)
        elif created_chat:
            # The chat was just created with a partial config; patch in acp_cwd.
            db.merge_chat_config(chat_id, {"acp_cwd": cwd})

        try:
            managed = await get_acp_manager().create(chat_id, agent_id, cwd)
        except Exception:
            if created_chat:
                db.delete_chat(chat_id)
            elif previous_config is not None:
                db.update_chat(chat_id, config=previous_config)
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
        # Probes are ephemeral and have no real chat, so fall back to the
        # default project directory rather than the backend's launch dir.
        from suzent.config import CONFIG

        probe_cwd = agent.cwd or str(
            Path(CONFIG.sandbox_data_path).resolve() / "projects" / "default"
        )
        Path(probe_cwd).mkdir(parents=True, exist_ok=True)
        probe_chat_id = f"probe:{agent_id}:{uuid.uuid4().hex}"
        managed = await manager.create(
            chat_id=probe_chat_id, agent_id=agent_id, cwd=probe_cwd
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
            data.get("cwd")
            or config.get("acp_cwd")
            or config.get("cwd")
            or _resolve_project_dir(chat_id)
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
