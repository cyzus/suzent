"""Request models are the source of truth for the generated client contract."""

from __future__ import annotations
import json
from typing import Annotated, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

MAX_ATTACHMENTS_PER_MESSAGE = 10


class MailboxPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: Annotated[StrictInt, Field(ge=0)] = 0
    limit: Annotated[StrictInt, Field(ge=1, le=100)] = 50
    category: Literal["notifications", "all", "external", "agent"] = "notifications"


class MailboxReadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[StrictInt, Field(gt=0)]] = Field(
        default_factory=list, max_length=100
    )
    all: StrictBool = False

    @model_validator(mode="after")
    def explicit_selection(self) -> MailboxReadRequest:
        if self.all == bool(self.ids):
            raise ValueError("Choose explicit ids or all")
        return self


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New conversation", min_length=1, max_length=200)
    project_id: str | None = Field(default=None, min_length=1, max_length=200)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_id: str = Field(min_length=1, max_length=200, pattern=r"^[^/]+$")


class SendRequest(ChatRequest):
    message: str = Field(default="", max_length=100000)
    model: str | None = Field(default=None, min_length=1, max_length=300)
    client_message_id: str | None = Field(default=None, min_length=1, max_length=100)
    attachments: list[Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]] = Field(
        default_factory=list, max_length=MAX_ATTACHMENTS_PER_MESSAGE
    )

    @model_validator(mode="after")
    def has_content(self) -> SendRequest:
        if not self.message.strip() and not self.attachments:
            raise ValueError("A message or an attachment is required")
        return self


class SteerRequest(ChatRequest):
    message: str = Field(min_length=1, max_length=100000, pattern=r"\S")
    model: str | None = Field(default=None, min_length=1, max_length=300)


class ManageRequest(ChatRequest):
    action: Literal["pin", "unpin", "rename", "move", "delete"]
    value: str | None = Field(default=None, min_length=1, max_length=200)


class MessageActionRequest(ChatRequest):
    action: Literal["retry", "edit", "fork"]
    message_index: Annotated[StrictInt, Field(ge=0)]
    text: str | None = Field(default=None, min_length=1, max_length=100000)
    model: str | None = Field(default=None, min_length=1, max_length=300)


class SurfaceAnswerRequest(ChatRequest):
    surface_id: str = Field(min_length=1, max_length=200)
    answer: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def bounded(self) -> SurfaceAnswerRequest:
        if len(json.dumps(self.answer, default=str)) > 100_000:
            raise ValueError("Answer too large")
        return self


class ObserveRequest(ChatRequest):
    wait_ms: int = Field(default=1000, ge=0, le=1000)
    protocol: Literal[1] = 1
    run_id: str | None = Field(default=None, max_length=200)
    after_seq: Annotated[StrictInt, Field(ge=0)] | None = None


class ChatPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["recent", "pinned", "project", "search"] = "recent"
    value: str = Field(default="", max_length=200)
    offset: int = Field(default=0, ge=0, le=10_000_000)
    limit: int = Field(default=30, ge=1, le=100)


class ChatStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ids: list[Annotated[str, Field(min_length=1, max_length=200)]] = Field(
        max_length=100
    )


class StarModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1, max_length=300)
    starred: StrictBool


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HostFieldsRequest(BaseModel):
    """Desktop-owned configuration stays opaque to the resource transport."""

    model_config = ConfigDict(extra="allow")


class ApiResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    ok: bool | None = None
    chat_id: str | None = None


class ApiChat(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    title: str
    messages: list[dict] | None = None
    model: str | None = None
    models: list[str] | None = None
    isRunning: bool | None = None
    projectId: str | None = None
    projectName: str | None = None
    pinned: bool | None = None
    platform: str | None = None
    unreadCount: int | None = None
    parentChatId: str | None = None
    regent: dict | None = None
    config: dict | None = None


class ApiChatList(BaseModel):
    chats: list[ApiChat]
    total: int | None = None
    nextOffset: int | None = None


class ApiProject(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    slug: str | None = None
    chatCount: int | None = None
    running: bool | None = None
    unread: bool | None = None


class ApiProjects(BaseModel):
    projects: list[ApiProject]


class ApiNavigation(ApiProjects):
    regent: ApiChat | None = None


class ApiModels(BaseModel):
    models: list[str]
    starredModels: list[str]
    canManage: bool
    success: bool = True
    defaultModel: str | None = None
    contextWindows: dict[str, int] = Field(default_factory=dict)
    providers: dict[str, int] = Field(default_factory=dict)


class ApiMailboxPage(BaseModel):
    items: list[dict]
    unread: int
    hasMore: bool


class ApiMailboxRead(BaseModel):
    marked: int
    unread: int


class ApiTasks(BaseModel):
    tasks: list[dict]


class ApiOverview(BaseModel):
    goal: dict | None = None
    tasks: list[dict]
    context: dict
    workQueue: list[dict] | None = None


class ApiApprovals(BaseModel):
    pending: list[dict]
    isRunning: bool


class ApiUploads(BaseModel):
    attachments: list[dict]


class ApiSession(BaseModel):
    model_config = ConfigDict(extra="allow")
    device: dict
    client_protocol: int
    stream_protocols: list[int]
    resource_api: int


class ApprovalChoice(ChatRequest):
    request_id: str = Field(min_length=1, max_length=200)
    action_id: str = Field(min_length=1, max_length=200)
    kind: Literal["tool", "acp"] = "tool"


class ApprovalBatch(ChatRequest):
    decisions: list[ApprovalChoice] = Field(min_length=1, max_length=64)
