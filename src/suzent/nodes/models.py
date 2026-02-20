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


class ConnectedResponse(BaseModel):
    """Server → Node: acknowledgment after successful registration."""

    type: str = "connected"
    node_id: str


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


class InvokeResponse(BaseModel):
    """POST /nodes/{node_id}/invoke response."""

    success: bool
    result: Any = None
    error: str | None = None
