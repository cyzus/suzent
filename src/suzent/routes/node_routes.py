"""
Routes for node management.

Provides:
- WebSocket endpoint for node connections (/ws/node)
- REST endpoints for listing, describing, and invoking nodes
"""

import asyncio
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
    """Authorize an incoming node connection (operator-gated pairing).

    Returns (authorized, device_token). On rejection, sends an ErrorResponse,
    closes the socket, and returns (False, ""). The device_token is non-empty
    only when a fresh approval mints one (to hand back to the node).

    A previously-approved device presents its durable token and reconnects
    silently. A new device blocks here until an operator approves or denies it
    (or the request times out).
    """
    if connect_msg.device_token and node_manager.device_store.verify(
        connect_msg.device_token
    ):
        return True, ""

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


def _get_peer_store(request):
    """Get (or lazily create) the controller-side PeerGrantStore."""
    app = getattr(request, "app", None)
    if app is None:
        return None
    store = getattr(app.state, "peer_store", None)
    if store is None:
        from suzent.nodes.peer_store import PeerGrantStore

        store = PeerGrantStore()
        app.state.peer_store = store
    return store


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

        # Gate the connection before registering. A new device blocks here
        # until an operator approves/denies (or the request times out); an
        # already-approved device reconnects on its durable token.
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


async def create_host_token(request: Request) -> JSONResponse:
    """POST /nodes/host-token — mint a full-access token for remote host control.

    Loopback-only (the auth boundary blocks remote callers from /nodes/* anyway).
    The token is returned once; copy it to the remote device. Revoke like any
    device. This is the deliberate, stronger credential for "use as the host" —
    distinct from scoped 'agent' grant tokens.
    """
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = str(body.get("name") or "").strip() or "Host token"
    device_id, token = node_manager.device_store.mint(name, "host", scope="full")
    return JSONResponse({"device_id": device_id, "token": token, "scope": "full"})


async def revoke_device(request: Request) -> JSONResponse:
    """POST /nodes/devices/{device_id}/revoke — Revoke a device's token.

    Best-effort notifies the holder (revocation propagation) so its UI/contact
    can update; the holder self-verifies, so the hint needn't be authenticated.
    """
    node_manager = _get_node_manager(request)
    device_id = request.path_params.get("device_id", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    # Capture the holder's callback before the record is gone.
    rec = node_manager.device_store.get_by_device_id(device_id)
    ok = node_manager.revoke_device(device_id)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "Unknown device"}, status_code=404
        )
    callback = (rec or {}).get("callback_url")
    if callback:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{callback}/channels/suzent/grant-changed", json={})
        except httpx.HTTPError:
            pass  # best-effort; the holder also discovers it on next call
    return JSONResponse({"success": True, "message": "Revoked"})


async def set_device_status(request: Request) -> JSONResponse:
    """POST /nodes/devices/{device_id}/status — pause/resume an issued grant.

    Body: {"status": "active" | "paused"}. Pausing keeps the durable token but
    denies the holder at the auth boundary; best-effort notifies the holder so
    its UI can re-verify (it self-verifies, so the hint needn't be authed).
    """
    node_manager = _get_node_manager(request)
    device_id = request.path_params.get("device_id", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    status = str(body.get("status") or "").strip()
    if status not in ("active", "paused"):
        return JSONResponse(
            {"error": "status must be active | paused"}, status_code=400
        )
    rec = node_manager.device_store.get_by_device_id(device_id)
    if not node_manager.device_store.set_status(device_id, status):
        return JSONResponse(
            {"success": False, "message": "Unknown device"}, status_code=404
        )
    callback = (rec or {}).get("callback_url")
    if callback:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(f"{callback}/channels/suzent/grant-changed", json={})
        except httpx.HTTPError:
            pass  # best-effort; the holder also discovers it on next call
    return JSONResponse({"success": True, "status": status})


# ─── Node auth configuration ─────────────────────────────────────────


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
    """GET /nodes/config — Current node configuration + pairing addresses."""
    from suzent.config import DEFAULT_PORT

    addresses = _pairing_addresses()
    primary = addresses[0] if addresses else None
    return JSONResponse(
        {
            "nodes_enabled": bool(CONFIG.nodes_enabled),
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
    """POST /nodes/config — Update node LAN exposure (persisted locally).

    Machine-specific settings live in local.yaml (never synced), the same
    place sandbox volumes are kept.
    """
    from suzent.routes.config_routes import (
        _load_local_config_file,
        _save_local_config_file,
    )

    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    cfg = _load_local_config_file()

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

    Body: {"gateway_url": "ws://host:port/ws/node", "name"?: str}

    The remote operator approves this device on first connect; no shared secret
    is required.
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


# ─── Control-grant: peer-to-peer agent control over HTTP ─────────────
#
# Two roles:
#   * Target (the device being controlled): exposes the bootstrap grant-request
#     / grant-status endpoints (auth-exempt) and operator approve/deny.
#   * Controller (the device doing the driving): initiates a control request,
#     stores the granted token, and triggers the peer's agent.


# -- Target side: bootstrap (AUTH-EXEMPT) + operator approval ---------


async def grant_request(request: Request) -> JSONResponse:
    """POST /nodes/grant-request — a remote peer asks to control this device.

    Auth-exempt bootstrap. Issues no token; only queues a request an operator
    must approve. Body: {"controller_name": str, "controller_addr"?: str}
    """
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = str(body.get("controller_name") or "").strip() or "unknown"
    host = request.client.host if request.client else ""
    addr = (
        _http_base(str(body.get("controller_addr") or ""))
        if body.get("controller_addr")
        else ""
    )
    identity = str(body.get("controller_identity") or "").strip()
    try:
        rid = node_manager.add_grant_request(
            name, host, controller_addr=addr, controller_identity=identity
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=429)
    return JSONResponse({"request_id": rid, "status": "pending"})


async def grant_status(request: Request) -> JSONResponse:
    """GET /nodes/grant-status/{request_id} — requester polls for the token.

    Auth-exempt; request_id is an unguessable capability. Token served once.
    """
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    rid = request.path_params.get("request_id", "")
    result = node_manager.take_grant_result(rid)
    if result is None:
        return JSONResponse({"error": "Unknown or expired request"}, status_code=404)
    return JSONResponse(result)


async def list_grants(request: Request) -> JSONResponse:
    """GET /nodes/grants — pending control requests (operator UI)."""
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"grants": [], "count": 0})
    grants = node_manager.list_grant_requests()
    return JSONResponse({"grants": grants, "count": len(grants)})


async def approve_grant(request: Request) -> JSONResponse:
    """POST /nodes/grants/{request_id}/approve — allow the peer to control us."""
    node_manager = _get_node_manager(request)
    rid = request.path_params.get("request_id", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    ok = node_manager.approve_grant(rid)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "Unknown or already-resolved request"},
            status_code=404,
        )
    return JSONResponse({"success": True, "message": "Approved"})


async def deny_grant(request: Request) -> JSONResponse:
    """POST /nodes/grants/{request_id}/deny."""
    node_manager = _get_node_manager(request)
    rid = request.path_params.get("request_id", "")
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    ok = node_manager.deny_grant(rid)
    if not ok:
        return JSONResponse(
            {"success": False, "message": "Unknown or already-resolved request"},
            status_code=404,
        )
    return JSONResponse({"success": True, "message": "Denied"})


# -- Controller side: initiate control, list peers, trigger -----------


def _http_base(addr: str) -> str:
    """Normalize a peer address to an http(s) base URL."""
    addr = (addr or "").strip().rstrip("/")
    if addr.startswith(("http://", "https://")):
        return addr
    if addr.startswith("ws://"):
        return "http://" + addr[len("ws://") :]
    if addr.startswith("wss://"):
        return "https://" + addr[len("wss://") :]
    return "http://" + addr


def _host_of(base_url: str) -> str:
    from urllib.parse import urlparse

    return (urlparse(base_url).hostname or base_url).strip()


def _is_tailscale_host(host: str) -> bool:
    return host.startswith("100.") or host.endswith(".ts.net")


def _my_base_for_peer(peer_base_url: str) -> str:
    """Pick an address of *this* server reachable on the peer's network.

    If we reach the peer over Tailscale, offer our Tailscale address (a LAN IP
    wouldn't be reachable from their network), otherwise our LAN address.
    """
    from suzent.config import DEFAULT_PORT

    if _is_tailscale_host(_host_of(peer_base_url)):
        for _label, host in _tailscale_addresses():
            if host.startswith("100."):
                return f"http://{host}:{DEFAULT_PORT}"
    return f"http://{_best_effort_lan_host()}:{DEFAULT_PORT}"


async def request_control(request: Request) -> JSONResponse:
    """POST /nodes/control — start controlling a peer (loopback/operator).

    Body: {"base_url": "http://host:port" | "ws://...", "name"?: str}
    Sends the peer a grant-request and returns its request_id to poll.
    """
    import httpx

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    base = _http_base(body.get("base_url") or "")
    if not base:
        return JSONResponse({"error": "base_url is required"}, status_code=400)

    import socket

    from suzent.nodes.node_identity import get_node_identity

    my_name = socket.gethostname()
    # Tell the grantor where to reach us (for revoke notifications), on the same
    # network we're reaching them.
    my_addr = _my_base_for_peer(base)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{base}/nodes/grant-request",
                json={
                    "controller_name": my_name,
                    "controller_addr": my_addr,
                    "controller_identity": get_node_identity(),
                },
            )
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Couldn't reach {base}: {e}"}, status_code=502)
    return JSONResponse(
        {"request_id": data.get("request_id"), "base_url": base, "status": "pending"}
    )


async def control_status(request: Request) -> JSONResponse:
    """GET /nodes/control-status?base_url=..&request_id=.. — poll + finalize.

    On approval, stores the peer locally and returns peer_id.
    """
    import httpx

    base = _http_base(request.query_params.get("base_url") or "")
    rid = request.query_params.get("request_id") or ""
    if not base or not rid:
        return JSONResponse(
            {"error": "base_url and request_id are required"}, status_code=400
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base}/nodes/grant-status/{rid}")
            if r.status_code == 404:
                return JSONResponse({"status": "expired"})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Couldn't reach {base}: {e}"}, status_code=502)

    status = data.get("status")
    if status == "approved" and data.get("token"):
        store = _get_peer_store(request)
        # Prefer a human name (from discovery) over the bare URL.
        name = (request.query_params.get("name") or "").strip() or _host_of(base)
        peer_id = store.add(name=name, base_url=base, token=data["token"])
        return JSONResponse({"status": "approved", "peer_id": peer_id})
    return JSONResponse({"status": status or "pending"})


async def list_peers(request: Request) -> JSONResponse:
    """GET /nodes/peers — peers this device can control, with live reachability."""
    from suzent.config import DEFAULT_PORT
    from suzent.nodes import discovery

    store = _get_peer_store(request)
    peers = store.list_peers() if store else []

    async def _probe(p):
        import httpx
        from urllib.parse import urlparse

        host = _host_of(p["base_url"])
        port = urlparse(p["base_url"]).port or DEFAULT_PORT
        online = await discovery.probe_reachable(host, port, timeout=1.5)
        p["online"] = online
        # Outbound status: is our grant token still accepted by the peer?
        #   offline → unreachable; revoked → reachable but token rejected;
        #   ready   → reachable and token valid.
        if not online:
            p["outbound_status"] = "offline"
            return
        rec = store.get(p["peer_id"]) if store else None
        token = (rec or {}).get("token")
        if not token:
            p["outbound_status"] = "revoked"
            return
        try:
            async with httpx.AsyncClient(timeout=4) as client:
                r = await client.get(
                    f"{p['base_url']}/channels/suzent/whoami",
                    headers={"Authorization": f"Bearer {token}"},
                )
            # whoami returns peer_id when the token maps to a live grant; a
            # revoked/paused token yields null (or 401/403).
            ok = r.status_code == 200 and bool((r.json() or {}).get("peer_id"))
            p["outbound_status"] = "ready" if ok else "revoked"
        except httpx.HTTPError:
            # Reachable a moment ago but the whoami failed — treat as offline
            # rather than falsely claiming revoked.
            p["outbound_status"] = "offline"

    await asyncio.gather(*(_probe(p) for p in peers), return_exceptions=True)
    return JSONResponse({"peers": peers, "count": len(peers)})


async def peer_invoke(request: Request) -> JSONResponse:
    """POST /nodes/peer-invoke — a controller runs a capability on US.

    Authenticated (agent-scope grant). Routes to one of our own local nodes that
    advertises the command, so a control grant can drive our hardware/agent just
    like a WS node could. Body: {"command", "params"?, "timeout"?}
    """
    node_manager = _get_node_manager(request)
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    command = (body.get("command") or "").strip()
    if not command:
        return JSONResponse({"error": "command is required"}, status_code=400)
    params = body.get("params") or {}
    timeout = body.get("timeout")

    target = next(
        (n for n in node_manager.nodes.values() if n.has_capability(command)), None
    )
    if not target:
        return JSONResponse(
            {"error": f"No local node provides '{command}'"}, status_code=404
        )
    try:
        result = await node_manager.invoke(
            target.node_id, command, params, timeout=timeout
        )
        return JSONResponse(result)
    except TimeoutError as e:
        return JSONResponse({"error": str(e)}, status_code=504)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def invoke_peer(request: Request) -> JSONResponse:
    """POST /nodes/peers/{peer_id}/invoke — run a capability on a peer (proxy).

    Body: {"command", "params"?, "timeout"?}. Calls the peer's /nodes/peer-invoke
    with our grant token. Lets `nodes invoke <peer> speaker.speak …` work.
    """
    import httpx

    store = _get_peer_store(request)
    peer_id = request.path_params.get("peer_id", "")
    peer = store.get(peer_id) if store else None
    if not peer:
        return JSONResponse({"error": "Unknown peer"}, status_code=404)
    if peer.get("mode") == "paused":
        return JSONResponse({"error": "Peer is paused"}, status_code=409)
    try:
        body = await request.json()
    except Exception:
        body = {}
    command = (body.get("command") or "").strip()
    if not command:
        return JSONResponse({"error": "command is required"}, status_code=400)

    payload = {"command": command, "params": body.get("params") or {}}
    if body.get("timeout") is not None:
        payload["timeout"] = body["timeout"]
    try:
        async with httpx.AsyncClient(timeout=body.get("timeout") or 60) as client:
            r = await client.post(
                f"{peer['base_url']}/nodes/peer-invoke",
                json=payload,
                headers={"Authorization": f"Bearer {peer['token']}"},
            )
            data = r.json()
            return JSONResponse(data, status_code=r.status_code)
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Couldn't reach peer: {e}"}, status_code=502)


async def peer_capabilities(request: Request) -> JSONResponse:
    """GET /nodes/peers/{peer_id}/capabilities — list a peer's hardware caps.

    Best-effort live fetch of the peer's own `GET /nodes` (its WS nodes and their
    capabilities) using our grant token. Returns {"capabilities": [...]} or an
    error the caller can render (e.g. peer offline). Read-only.
    """
    import httpx

    store = _get_peer_store(request)
    peer_id = request.path_params.get("peer_id", "")
    peer = store.get(peer_id) if store else None
    if not peer:
        return JSONResponse({"error": "Unknown peer"}, status_code=404)
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(
                f"{peer['base_url']}/nodes",
                headers={"Authorization": f"Bearer {peer['token']}"},
            )
        if r.status_code != 200:
            return JSONResponse(
                {"error": f"Peer returned {r.status_code}"}, status_code=502
            )
        nodes = r.json().get("nodes", [])
    except httpx.HTTPError as e:
        return JSONResponse({"error": f"Couldn't reach peer: {e}"}, status_code=502)
    # Flatten capabilities across the peer's local nodes.
    caps: list[dict] = []
    for n in nodes:
        for c in n.get("capabilities", []):
            caps.append({**c, "node": n.get("display_name", "")})
    return JSONResponse({"capabilities": caps, "count": len(caps)})


async def peer_offer(request: Request) -> JSONResponse:
    """POST /nodes/peer-offer — a controller we drive offers US a reverse grant.

    Authenticated (the offerer holds our token, so the auth boundary let it
    through). Body: {"name", "base_url", "token"}. We store it as a peer we can
    now drive too — the 'mutual' direction, from our side.
    """
    store = _get_peer_store(request)
    if not store:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)
    base = _http_base(body.get("base_url") or "")
    token = (body.get("token") or "").strip()
    if not base or not token:
        return JSONResponse(
            {"error": "base_url and token are required"}, status_code=400
        )
    store.add(name=body.get("name") or base, base_url=base, token=token)
    return JSONResponse({"success": True})


async def set_peer_mode(request: Request) -> JSONResponse:
    """POST /nodes/peers/{peer_id}/mode — off | trigger | paused.

    Controls the OUTBOUND direction (whether we may trigger this peer). The
    INBOUND direction (letting the peer drive us) is a separate reverse grant —
    see set_peer_reverse.
    """
    store = _get_peer_store(request)
    peer_id = request.path_params.get("peer_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    mode = str(body.get("mode") or "").strip()
    if mode not in ("off", "trigger", "paused"):
        return JSONResponse(
            {"error": "mode must be off | trigger | paused"}, status_code=400
        )
    if not store or not store.get(peer_id):
        return JSONResponse({"error": "Unknown peer"}, status_code=404)

    store.set_mode(peer_id, mode)
    return JSONResponse({"success": True, "mode": mode})


async def set_peer_reverse(request: Request) -> JSONResponse:
    """POST /nodes/peers/{peer_id}/reverse — let this peer drive us (inbound).

    Body: {"enabled": bool}. Enabling mints an agent-scope reverse token and
    offers it to the peer via /nodes/peer-offer so it can trigger our agent;
    disabling revokes that reverse token. This is the inbound half of a link
    (the old 'mutual' side-effect, now independently controllable).
    """
    import socket

    import httpx

    store = _get_peer_store(request)
    node_manager = _get_node_manager(request)
    peer_id = request.path_params.get("peer_id", "")
    try:
        body = await request.json()
    except Exception:
        body = {}
    enabled = bool(body.get("enabled"))
    peer = store.get(peer_id) if store else None
    if not peer:
        return JSONResponse({"error": "Unknown peer"}, status_code=404)
    if not node_manager:
        return JSONResponse({"error": "Node system not initialized"}, status_code=503)

    if enabled and not peer.get("reverse_device_id"):
        device_id, token = node_manager.device_store.mint(
            peer.get("name") or "peer", "peer", scope="agent"
        )
        # Offer an address reachable on the peer's network (Tailscale vs LAN).
        my_base = _my_base_for_peer(peer["base_url"])
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{peer['base_url']}/nodes/peer-offer",
                    json={
                        "name": socket.gethostname(),
                        "base_url": my_base,
                        "token": token,
                    },
                    headers={"Authorization": f"Bearer {peer['token']}"},
                )
                resp.raise_for_status()
            store.set_reverse_device_id(peer_id, device_id)
        except httpx.HTTPError as e:
            node_manager.device_store.revoke(device_id)
            return JSONResponse(
                {"error": f"Couldn't offer reverse grant to peer: {e}"},
                status_code=502,
            )
    elif not enabled and peer.get("reverse_device_id"):
        node_manager.device_store.revoke(peer["reverse_device_id"])
        store.set_reverse_device_id(peer_id, None)

    return JSONResponse({"success": True, "enabled": enabled})


async def remove_peer(request: Request) -> JSONResponse:
    """POST /nodes/peers/{peer_id}/remove — fully unlink a peer (both directions).

    Drops our outbound token AND revokes any reverse grant we issued so the peer
    can no longer drive us either. Removing a link severs it completely.
    """
    store = _get_peer_store(request)
    node_manager = _get_node_manager(request)
    peer_id = request.path_params.get("peer_id", "")
    peer = store.get(peer_id) if store else None
    if not peer:
        return JSONResponse({"error": "Unknown peer"}, status_code=404)
    # Revoke the inbound (reverse) grant first, if any.
    reverse_id = peer.get("reverse_device_id")
    if reverse_id and node_manager:
        node_manager.device_store.revoke(reverse_id)
    store.remove(peer_id)
    return JSONResponse({"success": True})


async def trigger_peer(request: Request):
    """POST /nodes/peers/{peer_id}/trigger — run a prompt on the peer, stream SSE.

    Body: {"prompt": str, "chat_id"?: str}. Sends through the peer's Suzent
    channel (/channels/suzent/inbound) — the peer keys the session by our
    authenticated identity and streams its agent's reply back.
    """
    from starlette.responses import StreamingResponse

    store = _get_peer_store(request)
    peer_id = request.path_params.get("peer_id", "")
    peer = store.get(peer_id) if store else None
    if not peer:
        return JSONResponse({"error": "Unknown peer"}, status_code=404)
    if peer.get("mode", "trigger") != "trigger":
        return JSONResponse(
            {"error": f"Peer triggering is {peer.get('mode')}"}, status_code=409
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    payload = {"content": prompt}
    if body.get("chat_id"):
        payload["chat_id"] = body["chat_id"]
    headers = {"Authorization": f"Bearer {peer['token']}"}
    url = f"{peer['base_url']}/channels/suzent/inbound"

    async def _stream():
        import httpx

        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream(
                    "POST", url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        yield f'data: {{"type":"error","data":"peer returned {resp.status_code}"}}\n\n'
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n"
        except httpx.HTTPError as e:
            yield f'data: {{"type":"error","data":"{e}"}}\n\n'

    return StreamingResponse(_stream(), media_type="text/event-stream")
