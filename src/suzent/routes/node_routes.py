"""
Routes for node management.

Provides:
- WebSocket endpoint for node connections (/ws/node)
- REST endpoints for listing, describing, and invoking nodes
"""

import uuid

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.websockets import WebSocket, WebSocketDisconnect

from suzent.logger import get_logger
from suzent.nodes.base import NodeCapability
from suzent.nodes.models import (
    ConnectMessage,
    ConnectedResponse,
    ErrorResponse,
    InvokeRequest,
    InvokeResponse,
    NodeInfo,
    NodeListResponse,
)
from suzent.nodes.ws_node import WebSocketNode

logger = get_logger(__name__)


def _get_node_manager(request_or_ws):
    """Get NodeManager from app state."""
    app = getattr(request_or_ws, "app", None)
    if app is None:
        return None
    return getattr(app.state, "node_manager", None)


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

        # Confirm connection
        resp = ConnectedResponse(node_id=node_id)
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
            node_id, invoke_req.command, invoke_req.params
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
