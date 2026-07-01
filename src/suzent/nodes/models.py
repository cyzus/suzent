"""
Pydantic models for the node system.

Covers:
- WebSocket protocol messages (connect, invoke, result, ping/pong)
- REST API request/response schemas
"""

from typing import Any

from pydantic import BaseModel, Field


# ─── WebSocket Protocol Messages ─────────────────────────────────────


class CapabilitySchema(BaseModel):
    """A single capability advertised by a node."""

    name: str
    description: str = ""
    params_schema: dict[str, str] = Field(default_factory=dict)


class ConnectMessage(BaseModel):
    """Node → Server: initial handshake on WebSocket connect."""

    type: str = "connect"
    display_name: str
    platform: str = "unknown"
    capabilities: list[CapabilitySchema] = Field(default_factory=list)
    # Durable per-device token previously minted by this server. When present
    # and valid, the node reconnects silently, skipping operator approval.
    device_token: str = ""


class ConnectedResponse(BaseModel):
    """Server → Node: acknowledgment after successful registration."""

    type: str = "connected"
    node_id: str
    # A freshly approved node receives a durable per-device token here. The node
    # should persist it and present it on reconnect.
    device_token: str = ""


class PendingResponse(BaseModel):
    """Server → Node: connection accepted but awaiting operator approval.

    Sent for a node the server has not seen before. The node
    keeps the socket open and waits for a subsequent ConnectedResponse
    (approved) or ErrorResponse (denied/timeout). ``pairing_code`` is the
    single-use, short-lived handle an operator uses to approve this connection.
    """

    type: str = "pending"
    pairing_code: str
    message: str = "Awaiting operator approval"


class InvokeMessage(BaseModel):
    """Server → Node: dispatch a command to the node."""

    type: str = "invoke"
    request_id: str
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class ResultMessage(BaseModel):
    """Node → Server: response to an invoked command."""

    type: str = "result"
    request_id: str
    success: bool = False
    result: Any = None
    error: str | None = None


class PingMessage(BaseModel):
    """Server → Node: heartbeat check."""

    type: str = "ping"


class PongMessage(BaseModel):
    """Node → Server: heartbeat response."""

    type: str = "pong"


class EventMessage(BaseModel):
    """Node → Server: unsolicited event from the node."""

    type: str = "event"
    event: str
    data: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    """Server → Node: protocol error."""

    type: str = "error"
    message: str


# ─── REST API Models ─────────────────────────────────────────────────


class NodeInfo(BaseModel):
    """Serialized node info for API responses."""

    node_id: str
    display_name: str
    platform: str
    status: str
    connected_at: str
    capabilities: list[CapabilitySchema]


class NodeListResponse(BaseModel):
    """GET /nodes response."""

    nodes: list[NodeInfo]
    count: int


class InvokeRequest(BaseModel):
    """POST /nodes/{node_id}/invoke request body."""

    command: str
    params: dict[str, Any] = Field(default_factory=dict)
    # Optional override for how long the server waits on the node's response.
    # Needed for long-running commands like agent.run; falls back to the node
    # default when omitted.
    timeout: float | None = None


class InvokeResponse(BaseModel):
    """POST /nodes/{node_id}/invoke response."""

    success: bool
    result: Any = None
    error: str | None = None


# ─── Pending / device-token API models ───────────────────────────────


class PendingNodeInfo(BaseModel):
    """A node awaiting operator approval (approve mode)."""

    pairing_code: str
    display_name: str
    platform: str
    capabilities: list[CapabilitySchema] = Field(default_factory=list)
    requested_at: str


class PendingListResponse(BaseModel):
    """GET /nodes/pending response."""

    pending: list[PendingNodeInfo]
    count: int


class ApprovedDeviceInfo(BaseModel):
    """A durably-approved device (has a per-device token)."""

    device_id: str
    display_name: str
    platform: str
    approved_at: str
    connected: bool = False


class ApprovedDeviceListResponse(BaseModel):
    """GET /nodes/devices response."""

    devices: list[ApprovedDeviceInfo]
    count: int


class PairingActionResponse(BaseModel):
    """Response for approve/deny/revoke actions."""

    success: bool
    message: str = ""
