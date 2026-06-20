"""
Inbound endpoint for the Suzent agent-to-agent channel (experimental).

A peer Suzent sends an agent message here; we run this device's agent for that
peer's session and stream AG-UI events back. "Start inline" per the migration
plan: the turn runs directly (like /chat) rather than through the SocialBrain
queue. Transport is gated by the auth boundary (agent scope); the application
allowlist is layered on in the pairing phase.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)


async def suzent_channel_inbound(request: Request):
    """POST /channels/suzent/inbound — run the agent for a peer, stream the reply.

    Body: {"from_id": <peer id>, "content": str, "chat_id"?: str}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    content = (body.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "content is required"}, status_code=400)

    # Identify the peer from its authenticated token (the contact/device id) —
    # decision §10.1: session keyed by peer id, not a spoofable body field. The
    # scoped device token *is* the per-peer authorization (no separate allowlist).
    peer_id = (body.get("from_id") or "peer").strip()
    try:
        from suzent.auth_boundary import extract_token

        nm = getattr(getattr(request, "app", None).state, "node_manager", None)
        token = extract_token(request.headers.raw)
        rec = nm.device_store.verify(token) if (nm and token) else None
        if rec:
            peer_id = rec.get("device_id", peer_id)
    except Exception:
        pass
    chat_id = body.get("chat_id") or f"suzent:{peer_id}"

    from suzent.agent_manager import build_agent_config
    from suzent.core.chat_processor import ChatProcessor

    processor = ChatProcessor()
    config_override = build_agent_config({}, require_social_tool=False)
    # A remote peer can't answer interactive tool approvals, so run headless and
    # auto-approve — a control grant means "drive this device's agent".
    config_override["interaction_profile"] = "headless"
    config_override["permission_mode"] = "auto"

    logger.info(f"Suzent channel: inbound turn for {chat_id}")
    generator = processor.process_turn(
        chat_id=chat_id,
        user_id=CONFIG.user_id,
        message_content=content,
        config_override=config_override,
    )
    return StreamingResponse(generator, media_type="text/event-stream")


async def suzent_channel_whoami(request: Request) -> JSONResponse:
    """GET /channels/suzent/whoami — lightweight token check for peers.

    Agent-scoped: a peer calls this with its grant token to confirm the token is
    still valid (used by revocation self-verification). Returns the peer id.
    """
    from suzent.auth_boundary import extract_token

    nm = getattr(getattr(request, "app", None).state, "node_manager", None)
    token = extract_token(request.headers.raw)
    rec = nm.device_store.verify(token) if (nm and token) else None
    return JSONResponse({"ok": True, "peer_id": (rec or {}).get("device_id")})


async def suzent_channel_grant_changed(request: Request) -> JSONResponse:
    """POST /channels/suzent/grant-changed — a grantor signals our access changed.

    Auth-exempt **hint** (not trusted): on receipt we re-verify each peer we hold
    a token for by calling its /whoami; peers whose token is now rejected are
    dropped. A spoofed notice just triggers a harmless re-check.
    """
    import httpx

    store = getattr(getattr(request, "app", None).state, "peer_store", None)
    if not store:
        return JSONResponse({"ok": True, "removed": 0})

    removed = 0
    for listed in store.list_peers():
        rec = store.get(listed["peer_id"])
        if not rec:
            continue
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{rec['base_url']}/channels/suzent/whoami",
                    headers={"Authorization": f"Bearer {rec['token']}"},
                )
            if r.status_code in (401, 403):
                store.remove(listed["peer_id"])
                removed += 1
        except httpx.HTTPError:
            pass  # unreachable != revoked — keep it
    if removed:
        logger.info(f"Suzent channel: dropped {removed} revoked peer(s)")
    return JSONResponse({"ok": True, "removed": removed})
