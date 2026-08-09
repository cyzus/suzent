"""
Inbound endpoint for the Suzent agent-to-agent channel (experimental).

A peer Suzent sends an agent message here; we run this device's agent for that
peer's session and stream AG-UI events back. "Start inline" per the migration
plan: the turn runs directly (like /chat) rather than through the SocialBrain
queue. Transport is gated by the auth boundary (agent scope); the application
allowlist is layered on in the pairing phase.
"""

from __future__ import annotations

import ipaddress
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from suzent.config import CONFIG
from suzent.logger import get_logger

logger = get_logger(__name__)

MAX_PEER_ATTACHMENTS = 8
MAX_PEER_ATTACHMENT_BYTES = 50 * 1024 * 1024
PEER_ATTACHMENT_TIMEOUT_SECONDS = 300.0


def _normalized_host(value: str | None) -> str:
    host = (value or "").rstrip(".").lower()
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        return host


def _validate_attachment_source(
    url: str,
    file_id: str,
    *,
    client_host: str,
    callback_url: str,
) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Attachment URL must use HTTP or HTTPS")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Attachment URL contains unsupported components")
    if parsed.path != f"/nodes/peer-files/{file_id}":
        raise ValueError("Attachment URL does not match its file id")

    allowed_hosts = {_normalized_host(client_host)}
    callback_host = urlparse(callback_url).hostname if callback_url else None
    if callback_host:
        allowed_hosts.add(_normalized_host(callback_host))
    if _normalized_host(parsed.hostname) not in allowed_hosts:
        raise ValueError("Attachment URL does not belong to the authenticated peer")


async def _download_peer_attachments(
    items: object,
    *,
    client_host: str,
    callback_url: str,
) -> tuple[list[dict], Path | None]:
    """Download authenticated peer artifacts into a disposable staging directory."""
    if not items:
        return [], None
    if not isinstance(items, list):
        raise ValueError("attachments must be a list")
    if len(items) > MAX_PEER_ATTACHMENTS:
        raise ValueError(f"At most {MAX_PEER_ATTACHMENTS} attachments are allowed")

    staging_dir = Path(tempfile.mkdtemp(prefix="suzent-peer-"))
    downloaded: list[dict] = []
    total_received = 0
    try:
        async with httpx.AsyncClient(
            timeout=PEER_ATTACHMENT_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            for item in items:
                if not isinstance(item, dict):
                    raise ValueError("Invalid attachment metadata")
                file_id = str(item.get("id") or "")
                url = str(item.get("url") or "")
                token = str(item.get("token") or "")
                name = Path(str(item.get("name") or "attachment")).name
                try:
                    advertised_size = int(item.get("size") or 0)
                except (TypeError, ValueError) as exc:
                    raise ValueError("Invalid attachment size") from exc
                if not file_id or not token or not name:
                    raise ValueError("Incomplete attachment metadata")
                if advertised_size < 0 or advertised_size > MAX_PEER_ATTACHMENT_BYTES:
                    raise ValueError(f"Attachment '{name}' exceeds the 50 MiB limit")
                _validate_attachment_source(
                    url,
                    file_id,
                    client_host=client_host,
                    callback_url=callback_url,
                )

                target = staging_dir / f"{file_id}_{name}"
                received = 0
                async with client.stream(
                    "GET", url, headers={"Authorization": f"Bearer {token}"}
                ) as response:
                    response.raise_for_status()
                    length = response.headers.get("content-length")
                    try:
                        content_length = int(length) if length else 0
                    except ValueError as exc:
                        raise ValueError("Invalid attachment Content-Length") from exc
                    if total_received + content_length > MAX_PEER_ATTACHMENT_BYTES:
                        raise ValueError(
                            "Peer attachments exceed the combined 50 MiB limit"
                        )
                    with target.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            received += len(chunk)
                            total_received += len(chunk)
                            if total_received > MAX_PEER_ATTACHMENT_BYTES:
                                raise ValueError(
                                    "Peer attachments exceed the combined 50 MiB limit"
                                )
                            output.write(chunk)
                if advertised_size and received != advertised_size:
                    raise ValueError(f"Attachment '{name}' size did not match metadata")
                media_type = str(item.get("media_type") or "application/octet-stream")
                downloaded.append(
                    {
                        "path": str(target),
                        "filename": name,
                        "type": "image" if media_type.startswith("image/") else "file",
                    }
                )
        return downloaded, staging_dir
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


async def suzent_channel_inbound(request: Request):
    """POST /channels/suzent/inbound — run the agent for a peer, stream the reply.

    Body: {"from_id": <peer id>, "content": str, "chat_id"?: str,
           "attachments"?: list[artifact reference]}
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    content = (body.get("content") or "").strip()
    if not content:
        return JSONResponse({"error": "content is required"}, status_code=400)

    # Resolve the node manager once (None-safe: request.app may be unset in tests).
    app = getattr(request, "app", None)
    nm = getattr(getattr(app, "state", None), "node_manager", None)

    # Identify the peer from its authenticated token (the contact/device id) —
    # decision §10.1: session keyed by the *authenticated* identity, never a
    # spoofable body field. The scoped device token is the per-peer authorization.
    rec = None
    try:
        from suzent.auth_boundary import extract_token

        token = extract_token(request.headers.raw)
        rec = nm.device_store.verify(token) if (nm and token) else None
    except Exception:
        pass

    # Require an identified peer (valid token) — otherwise we'd key the session by
    # a spoofable body field and create empty/orphan chats for unauthenticated
    # callers. A loopback caller (local app/tests) may pass an explicit chat_id.
    peer_id = rec.get("device_id") if rec else None
    chat_id = body.get("chat_id") or (f"suzent:{peer_id}" if peer_id else None)
    if not chat_id:
        # Record the rejected attempt so the operator can spot probing/abuse.
        if nm is not None:
            client_host = request.client.host if request.client else ""
            nm.record_unauthorized_trigger(client_host, str(body.get("from_id") or ""))
        return JSONResponse(
            {"error": "Unauthorized: a valid peer token (or chat_id) is required"},
            status_code=401,
        )

    # Stamp usage on the grant so the Devices tab can show last-active + count.
    if peer_id and nm is not None:
        try:
            nm.device_store.record_trigger(peer_id)
        except Exception:
            pass
    name = (rec or {}).get("display_name") if rec else None
    trigger_label = name or peer_id or "an unknown device"

    attachment_files: list[dict] = []
    attachment_staging_dir: Path | None = None
    try:
        attachment_files, attachment_staging_dir = await _download_peer_attachments(
            body.get("attachments"),
            client_host=request.client.host if request.client else "",
            callback_url=str((rec or {}).get("callback_url") or ""),
        )
    except (httpx.HTTPError, OSError, ValueError) as exc:
        logger.warning("Suzent channel: peer attachment download rejected: {}", exc)
        return JSONResponse(
            {"error": f"Could not retrieve peer attachment: {exc}"},
            status_code=400,
        )

    from suzent.agent_manager import build_agent_config
    from suzent.core.chat_processor import ChatProcessor
    from suzent.database import get_database

    # process_turn only *updates* an existing chat row — a brand-new peer session
    # would otherwise persist nothing (invisible in the UI) and carry no memory.
    # Shared with SocialBrain: tag platform, place in the Social project, so the
    # session shows in the chat list and later triggers to this chat_id resume
    # its history.
    db = get_database()
    created_now = db.ensure_channel_chat(
        chat_id,
        title=f"⇄ {trigger_label}",
        platform="suzent",
        config_extra={"sender_id": peer_id or "", "sender_name": trigger_label},
    )

    processor = ChatProcessor()
    config_override = build_agent_config({}, require_social_tool=False)
    # A remote peer can't answer interactive tool approvals, so run headless and
    # auto-approve — a control grant means "drive this device's agent".
    config_override["interaction_profile"] = "headless"
    config_override["permission_mode"] = "auto"

    # Attribution: inject who is driving this turn as a hidden system-reminder
    # (out-of-band context, not part of the visible message) so the agent knows
    # it's a remote peer, not the local user.
    attribution = (
        f"This turn was triggered remotely by peer device '{trigger_label}' over "
        f"the Suzent agent-to-agent channel — not by the local user. Respond as if "
        f"assisting that peer."
    )

    logger.info(f"Suzent channel: inbound turn for {chat_id} (from {trigger_label})")
    generator = processor.process_turn(
        chat_id=chat_id,
        user_id=CONFIG.user_id,
        message_content=content,
        files=attachment_files,
        config_override=config_override,
        system_reminders=[attribution],
    )

    # Tee the turn: stream it back to the calling peer (HTTP response) AND mirror
    # each event onto this device's background bus so *our* UI surfaces the
    # session live (new chat + streaming reply), like a local /chat/send turn.
    from suzent.core.stream_registry import (
        register_background_stream,
        is_background_streaming,
    )

    bus_queue = (
        None
        if is_background_streaming(chat_id)
        else register_background_stream(chat_id)
    )

    async def _teed():
        try:
            async for chunk in generator:
                if bus_queue is not None:
                    try:
                        await bus_queue.put(chunk)
                    except Exception:
                        pass
                yield chunk
        except Exception as exc:
            # Frame the error like /chat/send does so the peer AND our local UI
            # see a RUN_ERROR instead of a silent stream end.
            logger.error(f"Suzent channel: turn failed for {chat_id}: {exc}")
            import json as _json

            err = f'data: {{"type":"RUN_ERROR","message":{_json.dumps(str(exc))}}}\n\n'
            if bus_queue is not None:
                try:
                    await bus_queue.put(err)
                except Exception:
                    pass
            yield err
        finally:
            if bus_queue is not None:
                try:
                    await bus_queue.put(None)
                except Exception:
                    pass
            # If we created the chat for this call but the turn persisted nothing
            # (errored / produced no output), drop the orphan empty row.
            if created_now:
                try:
                    chat = db.get_chat(chat_id)
                    if (
                        chat is not None
                        and not (chat.messages or [])
                        and not chat.agent_state
                    ):
                        db.delete_chat(chat_id)
                        logger.info(f"Suzent channel: removed empty chat {chat_id}")
                except Exception:
                    pass
            if attachment_staging_dir is not None:
                shutil.rmtree(attachment_staging_dir, ignore_errors=True)

    return StreamingResponse(_teed(), media_type="text/event-stream")


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
