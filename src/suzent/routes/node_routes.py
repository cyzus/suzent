"""
Routes for node management.

Provides:
- WebSocket endpoint for node connections (/ws/node)
- REST endpoints for listing, describing, and invoking nodes
"""

import asyncio
import hmac
import uuid

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.config import CONFIG
from suzent.logger import get_logger
from suzent.nodes.base import NodeCapability
from suzent.nodes.manager import PENDING_TTL_SECONDS
from suzent.nodes.models import (
    ConnectMessage,
    ConnectedResponse,
    ErrorResponse,
    InvokeRequest,
    InvokeResponse,
    NodeInfo,
    NodeListResponse,
    PendingResponse,
)
from suzent.nodes.ws_node import WebSocketNode

logger = get_logger(__name__)


async def _authorize_node(
    websocket: WebSocket,
    node_manager,
    connect_msg: ConnectMessage,
    capabilities: list[NodeCapability],
) -> tuple[bool, str]:
    """Apply node_auth_mode to an incoming connection.

    Returns (authorized, device_token). On rejection, sends an ErrorResponse,
    closes the socket, and returns (False, ""). The device_token is non-empty
    only when approve mode freshly mints one (to hand back to the node).
    """
    mode = (CONFIG.node_auth_mode or "open").lower()

    # A previously-approved device presents its durable token and skips
    # straight through, regardless of open/token/approve.
    if connect_msg.device_token and node_manager.device_store.verify(
        connect_msg.device_token
    ):
        return True, ""

    if mode == "open":
        return True, ""

    if mode == "token":
        expected = CONFIG.node_auth_token or ""
        # Fail closed: an empty server token never authorizes anyone.
        if expected and hmac.compare_digest(connect_msg.auth_token or "", expected):
            return True, ""
        await _reject(websocket, "Invalid or missing node auth token")
        return False, ""

    if mode == "approve":
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        code = node_manager.add_pending(
            connect_msg.display_name, connect_msg.platform, capabilities, future
        )
        await websocket.send_json(PendingResponse(pairing_code=code).model_dump())
        try:
            outcome = await asyncio.wait_for(future, timeout=PENDING_TTL_SECONDS)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            node_manager.cancel_pending(code)
            await _reject(websocket, "Approval timed out")
            return False, ""
        if outcome:  # truthy = device_token string
            return True, str(outcome)
        await _reject(websocket, "Connection denied by operator")
        return False, ""

    # Unknown mode → fail closed.
    await _reject(websocket, f"Unsupported node_auth_mode: {mode}")
    return False, ""


async def _reject(websocket: WebSocket, message: str) -> None:
    try:
        await websocket.send_json(ErrorResponse(message=message).model_dump())
        await websocket.close(code=1008, reason=message[:120])
    except Exception:
        pass


def _get_node_manager(request_or_ws):
    """Get NodeManager from app state."""
    app = getattr(request_or_ws, "app", None)
    if app is None:
        return None
    return getattr(app.state, "node_manager", None)


def _get_outbound_manager(request):
    """Get (or lazily create) the OutboundConnectionManager from app state."""
    app = getattr(request, "app", None)
    if app is None:
        return None
    mgr = getattr(app.state, "outbound_manager", None)
    if mgr is None:
        from suzent.nodes.outbound import OutboundConnectionManager

        mgr = OutboundConnectionManager()
        app.state.outbound_manager = mgr
    return mgr


async def node_websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for node connections.

    Handshake protocol:
        1. Node connects to /ws/node
        2. Node sends: {"type": "connect", "display_name": "...", "platform": "...",
                        "capabilities": [{"name": "...", "description": "...", "params_schema": {...}}]}
        3. Server responds: {"type": "connected", "node_id": "..."}
        4. Bidirectional message loop for invocations and results
    """
    node_manager = _get_node_manager(websocket)
    if not node_manager:
        await websocket.close(code=1011, reason="Node system not initialized")
        return

    await websocket.accept()
    node = None

    try:
        # Wait for the connect handshake
        data = await websocket.receive_json()

        if data.get("type") != "connect":
            err = ErrorResponse(message="Expected 'connect' message")
            await websocket.send_json(err.model_dump())
            await websocket.close(code=1002, reason="Invalid handshake")
            return

        # Validate with Pydantic
        try:
            connect_msg = ConnectMessage(**data)
        except ValidationError as e:
            err = ErrorResponse(message=f"Invalid connect message: {e}")
            await websocket.send_json(err.model_dump())
            await websocket.close(code=1002, reason="Invalid handshake")
            return

        # Convert to internal NodeCapability objects
        capabilities = [
            NodeCapability(
                name=cap.name,
                description=cap.description,
                params_schema=cap.params_schema,
            )
            for cap in connect_msg.capabilities
        ]

        # Enforce node_auth_mode before registering. Approve mode blocks here
        # until an operator approves/denies (or the request times out).
        authorized, device_token = await _authorize_node(
            websocket, node_manager, connect_msg, capabilities
        )
        if not authorized:
            return

        # Create node
        node_id = str(uuid.uuid4())
        node = WebSocketNode(
            websocket=websocket,
            node_id=node_id,
            display_name=connect_msg.display_name,
            platform=connect_msg.platform,
            capabilities=capabilities,
        )

        node_manager.register_node(node)

        # Confirm connection (handing back a freshly-minted device token, if any)
        resp = ConnectedResponse(node_id=node_id, device_token=device_token)
        await websocket.send_json(resp.model_dump())

        logger.info(
            f"Node '{connect_msg.display_name}' connected "
            f"({connect_msg.platform}, {len(capabilities)} capabilities)"
        )

        # Message loop
        while True:
            data = await websocket.receive_json()
            node.handle_message(data)

    except WebSocketDisconnect:
        logger.info(
            f"Node WebSocket disconnected: {node.display_name if node else 'unknown'}"
        )
    except Exception as e:
        logger.error(f"Node WebSocket error: {e}")
    finally:
        if node and node_manager:
            node_manager.unregister_node(node.node_id)


async def list_nodes(request: Request) -> JSONResponse:
    """GET /nodes — List all connected nodes."""
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"nodes": [], "error": "Node system not initialized"})

    nodes = node_manager.list_nodes()
    resp = NodeListResponse(
        nodes=[NodeInfo(**n) for n in nodes],
        count=len(nodes),
    )
    return JSONResponse(resp.model_dump())


async def describe_node(request: Request) -> JSONResponse:
    """GET /nodes/{node_id} — Get detailed info about a specific node."""
    node_manager = _get_node_manager(request)
    node_id = request.path_params.get("node_id", "")

    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)

    info = node_manager.describe_node(node_id)
    if not info:
        return JSONResponse({"error": f"Node not found: {node_id}"}, status_code=404)

    return JSONResponse(info)


async def invoke_node_command(request: Request) -> JSONResponse:
    """
    POST /nodes/{node_id}/invoke — Invoke a command on a node.

    Body: {"command": "camera.snap", "params": {"format": "png"}}
    """
    node_manager = _get_node_manager(request)
    node_id = request.path_params.get("node_id", "")

    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)

    try:
        body = await request.json()
        invoke_req = InvokeRequest(**body)
    except ValidationError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    try:
        result = await node_manager.invoke(
            node_id, invoke_req.command, invoke_req.params, timeout=invoke_req.timeout
        )
        resp = InvokeResponse(**result)
        return JSONResponse(resp.model_dump())
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except TimeoutError as e:
        return JSONResponse({"error": str(e)}, status_code=504)
    except ConnectionError as e:
        return JSONResponse({"error": str(e)}, status_code=502)
    except Exception as e:
        logger.error(f"Error invoking node command: {e}")
        return JSONResponse({"error": f"Internal error: {e}"}, status_code=500)


# ─── Approve-mode pairing & device management ────────────────────────


async def list_pending_nodes(request: Request) -> JSONResponse:
    """GET /nodes/pending — Connections awaiting operator approval."""
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"pending": [], "count": 0})
    pending = node_manager.list_pending()
    return JSONResponse({"pending": pending, "count": len(pending)})


async def approve_pending_node(request: Request) -> JSONResponse:
    """POST /nodes/pending/{pairing_code}/approve — Approve a pending node."""
    node_manager = _get_node_manager(request)
    code = request.path_params.get("pairing_code", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    ok, _token = node_manager.approve_pending(code)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "Unknown or expired pairing code"},
            status_code=404,
        )
    return JSONResponse({"success": True, "message": "Approved"})


async def deny_pending_node(request: Request) -> JSONResponse:
    """POST /nodes/pending/{pairing_code}/deny — Deny a pending node."""
    node_manager = _get_node_manager(request)
    code = request.path_params.get("pairing_code", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    ok = node_manager.deny_pending(code)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "Unknown or expired pairing code"},
            status_code=404,
        )
    return JSONResponse({"success": True, "message": "Denied"})


async def list_approved_devices(request: Request) -> JSONResponse:
    """GET /nodes/devices — Durably-approved devices (per-device tokens)."""
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"devices": [], "count": 0})
    devices = node_manager.list_devices()
    return JSONResponse({"devices": devices, "count": len(devices)})


async def revoke_device(request: Request) -> JSONResponse:
    """POST /nodes/devices/{device_id}/revoke — Revoke a device's token."""
    node_manager = _get_node_manager(request)
    device_id = request.path_params.get("device_id", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    ok = node_manager.revoke_device(device_id)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "Unknown device"}, status_code=404
        )
    return JSONResponse({"success": True, "message": "Revoked"})


# ─── Node auth configuration ─────────────────────────────────────────

_VALID_AUTH_MODES = ("open", "token", "approve")


def _best_effort_lan_host() -> str:
    """Best-effort LAN IP another device can use to reach this server.

    Falls back to the configured host when detection fails (e.g. offline).
    """
    import socket

    from suzent.config import DEFAULT_HOST

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # No packets are actually sent; this just picks the outbound iface.
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return DEFAULT_HOST


def _tailscale_addresses() -> list[tuple[str, str]]:
    """Detect this machine's Tailscale address(es) via the local CLI.

    Returns a list of (label, host) — the 100.x IP and, when available, the
    MagicDNS name. Empty when Tailscale isn't installed/up. Best-effort: a
    short subprocess timeout, never raises.
    """
    import json
    import os
    import shutil
    import subprocess

    exe = shutil.which("tailscale")
    if not exe:
        mac_path = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
        if os.path.exists(mac_path):
            exe = mac_path
    if not exe:
        return []

    out: list[tuple[str, str]] = []
    try:
        ip_res = subprocess.run(
            [exe, "ip", "-4"], capture_output=True, text=True, timeout=2
        )
        ip = (ip_res.stdout or "").strip().splitlines()
        if ip and ip[0].strip():
            out.append(("Tailscale", ip[0].strip()))
    except Exception:
        return out

    # MagicDNS name (nice, stable across IP changes) — optional.
    try:
        st = subprocess.run(
            [exe, "status", "--json"], capture_output=True, text=True, timeout=2
        )
        data = json.loads(st.stdout or "{}")
        dns = (data.get("Self", {}) or {}).get("DNSName", "")
        if dns:
            out.append(("Tailscale (MagicDNS)", dns.rstrip(".")))
    except Exception:
        pass

    return out


def _pairing_addresses() -> list[dict]:
    """Candidate addresses a companion device can use to reach this server."""
    from suzent.config import DEFAULT_PORT

    candidates: list[tuple[str, str]] = [("LAN", _best_effort_lan_host())]
    candidates.extend(_tailscale_addresses())

    seen: set[str] = set()
    result = []
    for label, host in candidates:
        if not host or host in seen:
            continue
        seen.add(host)
        result.append(
            {
                "label": label,
                "host": host,
                "gateway_url": f"ws://{host}:{DEFAULT_PORT}/ws/node",
            }
        )
    return result


async def get_node_config(request: Request) -> JSONResponse:
    """GET /nodes/config — Current node auth configuration + pairing addresses."""
    from suzent.config import DEFAULT_PORT
    from suzent.auth_boundary import is_loopback

    addresses = _pairing_addresses()
    primary = addresses[0] if addresses else None
    # Only reveal the shared secret to the local app (loopback). A remote caller
    # must never be able to read it back, even with a valid token.
    client_host = request.client.host if request.client else ""
    token_visible = CONFIG.node_auth_token or "" if is_loopback(client_host) else ""
    return JSONResponse(
        {
            "nodes_enabled": bool(CONFIG.nodes_enabled),
            "node_auth_mode": (CONFIG.node_auth_mode or "open"),
            # Surfaced to the local operator only (see token_visible above).
            "node_auth_token": token_visible,
            "node_auth_token_set": bool(CONFIG.node_auth_token),
            "node_lan_bind": bool(getattr(CONFIG, "node_lan_bind", False)),
            "port": DEFAULT_PORT,
            # All reachable addresses (LAN + Tailscale if present) so the UI can
            # offer the right one per network. lan_host/gateway_url kept for
            # backward compatibility.
            "addresses": addresses,
            "lan_host": primary["host"] if primary else "",
            "gateway_url": primary["gateway_url"] if primary else "",
        }
    )


async def save_node_config(request: Request) -> JSONResponse:
    """POST /nodes/config — Update node auth mode/token (persisted locally).

    Secrets and machine-specific auth live in local.yaml (never synced), the
    same place sandbox volumes are kept.
    """
    import secrets

    from suzent.routes.config_routes import (
        _load_local_config_file,
        _save_local_config_file,
    )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    cfg = _load_local_config_file()

    mode = payload.get("node_auth_mode")
    if mode is not None:
        if mode not in _VALID_AUTH_MODES:
            return JSONResponse(
                {"error": f"node_auth_mode must be one of {_VALID_AUTH_MODES}"},
                status_code=400,
            )
        cfg["node_auth_mode"] = mode
        CONFIG.node_auth_mode = mode

    # Either set an explicit token or ask the server to generate a strong one.
    if payload.get("regenerate"):
        token = secrets.token_urlsafe(24)
        cfg["node_auth_token"] = token
        CONFIG.node_auth_token = token
    elif payload.get("node_auth_token") is not None:
        token = str(payload["node_auth_token"])
        cfg["node_auth_token"] = token
        CONFIG.node_auth_token = token

    # LAN/Tailscale exposure. Takes effect on next server restart (the bind host
    # is fixed once uvicorn is listening).
    restart_required = False
    if payload.get("node_lan_bind") is not None:
        val = bool(payload["node_lan_bind"])
        if val != bool(getattr(CONFIG, "node_lan_bind", False)):
            restart_required = True
        cfg["node_lan_bind"] = val
        CONFIG.node_lan_bind = val

    _save_local_config_file(cfg)
    return JSONResponse(
        {
            "success": True,
            "node_auth_mode": CONFIG.node_auth_mode or "open",
            "node_auth_token": CONFIG.node_auth_token or "",
            "node_lan_bind": bool(getattr(CONFIG, "node_lan_bind", False)),
            "restart_required": restart_required,
        }
    )


# ─── Discovery & outbound (click-to-pair) ────────────────────────────


async def discover_nodes(request: Request) -> JSONResponse:
    """GET /nodes/discover — Find Suzent peers on the LAN (mDNS) and tailnet."""
    from suzent.config import DEFAULT_PORT
    from suzent.nodes import discovery

    try:
        lan_timeout = float(request.query_params.get("timeout", "2.0"))
    except ValueError:
        lan_timeout = 2.0
    lan_timeout = max(0.5, min(lan_timeout, 5.0))

    result = await discovery.discover_all(
        self_port=DEFAULT_PORT, lan_timeout=lan_timeout
    )
    return JSONResponse(result)


async def connect_node(request: Request) -> JSONResponse:
    """POST /nodes/connect — Join a remote Suzent as a node (outbound).

    Body: {"gateway_url": "ws://host:port/ws/node", "name"?: str, "token"?: str}
    """
    mgr = _get_outbound_manager(request)
    if not mgr:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    gateway_url = (body.get("gateway_url") or "").strip()
    if not gateway_url:
        return JSONResponse({"error": "gateway_url is required"}, status_code=400)

    # Probe first so an unreachable gateway fails loudly here, instead of the
    # NodeHost retrying silently in the background (target sees nothing).
    from urllib.parse import urlparse

    from suzent.config import DEFAULT_PORT
    from suzent.nodes import discovery

    parsed = urlparse(gateway_url)
    probe_host, probe_port = parsed.hostname, parsed.port or DEFAULT_PORT
    if probe_host and not await discovery.probe_reachable(
        probe_host, probe_port, timeout=2.0
    ):
        return JSONResponse(
            {
                "error": (
                    f"Can't reach {probe_host}:{probe_port}. On the other device, "
                    f"enable Settings → Devices → 'Reachable by other devices' "
                    f"and restart it (the app binds localhost only by default)."
                )
            },
            status_code=502,
        )

    host = mgr.start(
        gateway_url,
        display_name=(body.get("name") or "").strip(),
        token=(body.get("token") or "").strip(),
    )
    return JSONResponse(
        {
            "success": True,
            "gateway_url": gateway_url,
            "display_name": host.display_name,
            "status": host.status,
        }
    )


async def list_connections(request: Request) -> JSONResponse:
    """GET /nodes/connections — Outbound connections this device initiated."""
    mgr = _get_outbound_manager(request)
    if not mgr:
        return JSONResponse({"connections": [], "count": 0})
    conns = mgr.list()
    return JSONResponse({"connections": conns, "count": len(conns)})


async def disconnect_node(request: Request) -> JSONResponse:
    """POST /nodes/connect/stop — Stop an outbound connection.

    Body: {"gateway_url": "ws://host:port/ws/node"}
    """
    mgr = _get_outbound_manager(request)
    if not mgr:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    gateway_url = (body.get("gateway_url") or "").strip()
    ok = await mgr.stop(gateway_url)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "No such connection"}, status_code=404
        )
    return JSONResponse({"success": True, "message": "Disconnected"})
