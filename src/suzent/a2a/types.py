"""
Wire models for the A2A (Agent2Agent) protocol, JSON-RPC binding.

These mirror the A2A specification's JSON-RPC dialect exactly: field names
serialize as camelCase, ``kind`` discriminators are present on every polymorphic
member, and the task states use the hyphenated spelling (``input-required``, not
``TASK_STATE_INPUT_REQUIRED`` — that is the gRPC enum, a different binding).

We hand-roll rather than depend on ``a2a-sdk`` at runtime: the SDK pulls in
grpcio/protobuf and ships an opinionated server framework that would fight the
Starlette route style used everywhere else here. Conformance is not left to
trust — ``tests/a2a/test_sdk_conformance.py`` drives this server with the real
SDK client, which is a dev-only dependency.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# The JSON-RPC binding in the wild (and in the official SDK's JSON-RPC client)
# speaks the 0.3.0 method vocabulary. The 1.0 release renamed methods only for
# the gRPC/REST bindings; `message/send` remains the JSON-RPC spelling.
PROTOCOL_VERSION = "0.3.0"

TRANSPORT_JSONRPC = "JSONRPC"


class A2AModel(BaseModel):
    """Base: camelCase on the wire, snake_case in Python, both accepted in."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# ─── Parts, messages, artifacts ──────────────────────────────────────


class TextPart(A2AModel):
    kind: Literal["text"] = "text"
    text: str
    metadata: dict[str, Any] | None = None


class FileWithUri(A2AModel):
    uri: str
    name: str | None = None
    mime_type: str | None = None


class FileWithBytes(A2AModel):
    bytes: str  # base64
    name: str | None = None
    mime_type: str | None = None


class FilePart(A2AModel):
    kind: Literal["file"] = "file"
    file: FileWithBytes | FileWithUri
    metadata: dict[str, Any] | None = None


class DataPart(A2AModel):
    kind: Literal["data"] = "data"
    data: dict[str, Any]
    metadata: dict[str, Any] | None = None


Part = Annotated[TextPart | FilePart | DataPart, Field(discriminator="kind")]


class Role(str, Enum):
    user = "user"
    agent = "agent"


class Message(A2AModel):
    kind: Literal["message"] = "message"
    message_id: str
    role: Role
    parts: list[Part]
    context_id: str | None = None
    task_id: str | None = None
    reference_task_ids: list[str] | None = None
    extensions: list[str] | None = None
    metadata: dict[str, Any] | None = None

    def text(self) -> str:
        """Flatten the text parts — what our agent actually consumes."""
        return "\n".join(p.text for p in self.parts if isinstance(p, TextPart)).strip()


class Artifact(A2AModel):
    artifact_id: str
    parts: list[Part]
    name: str | None = None
    description: str | None = None
    extensions: list[str] | None = None
    metadata: dict[str, Any] | None = None


# ─── Task lifecycle ──────────────────────────────────────────────────


class TaskState(str, Enum):
    """Lifecycle states. `input-required` and `auth-required` are *interrupted*
    (the client must act); the rest of the non-`working` states are terminal."""

    submitted = "submitted"
    working = "working"
    input_required = "input-required"
    auth_required = "auth-required"
    completed = "completed"
    canceled = "canceled"
    failed = "failed"
    rejected = "rejected"
    unknown = "unknown"

    @property
    def is_terminal(self) -> bool:
        return self in _TERMINAL_STATES

    @property
    def is_interrupted(self) -> bool:
        return self in _INTERRUPTED_STATES


_TERMINAL_STATES = frozenset(
    {
        TaskState.completed,
        TaskState.canceled,
        TaskState.failed,
        TaskState.rejected,
    }
)
_INTERRUPTED_STATES = frozenset({TaskState.input_required, TaskState.auth_required})


class TaskStatus(A2AModel):
    state: TaskState
    message: Message | None = None
    timestamp: str | None = None


class Task(A2AModel):
    kind: Literal["task"] = "task"
    id: str
    context_id: str
    status: TaskStatus
    artifacts: list[Artifact] | None = None
    history: list[Message] | None = None
    metadata: dict[str, Any] | None = None


class TaskStatusUpdateEvent(A2AModel):
    kind: Literal["status-update"] = "status-update"
    task_id: str
    context_id: str
    status: TaskStatus
    final: bool = False
    metadata: dict[str, Any] | None = None


class TaskArtifactUpdateEvent(A2AModel):
    kind: Literal["artifact-update"] = "artifact-update"
    task_id: str
    context_id: str
    artifact: Artifact
    append: bool = False
    last_chunk: bool = False
    metadata: dict[str, Any] | None = None
