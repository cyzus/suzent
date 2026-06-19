from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PermissionMode(str, Enum):
    DEFAULT = "default"
    STRICT_READONLY = "strict_readonly"
    ACCEPT_EDITS = "accept_edits"
    FULL_APPROVAL = "full_approval"
    PLAN = "plan"
    AUTO = "auto"


class CommandDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class PermissionRisk(str, Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionScope(str, Enum):
    ONCE = "once"
    SESSION = "session"
    GLOBAL = "global"


class PermissionFeedbackKind(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"


class CommandClass(str, Enum):
    READ_ONLY = "read_only"
    WRITE_LIMITED = "write_limited"
    DANGEROUS = "dangerous"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BashCommandPolicyRule:
    pattern: str
    match_type: Literal["exact", "prefix"]
    action: CommandDecision


@dataclass(frozen=True)
class CommandContext:
    raw: str
    tokens: list[str]
    base_command: str
    args: list[str]
    redirections: list[str]
    has_control_operators: bool


@dataclass(frozen=True)
class PathUse:
    path: str
    operation: Literal["read", "write", "cwd", "delete"]


@dataclass
class PermissionEvaluation:
    decision: CommandDecision
    reason: str
    command_class: CommandClass
    metadata: dict[str, Any] = field(default_factory=dict)


class PermissionUpdate(BaseModel):
    """A backend-owned permission mutation offered by an approval action."""

    model_config = ConfigDict(populate_by_name=True)

    type: Literal["add_rule", "set_mode"]
    destination: Literal["session", "global"]
    payload: dict[str, Any] = Field(default_factory=dict)


class PermissionAction(BaseModel):
    """One action the client may select for a pending permission request."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    behavior: Literal["allow", "deny"]
    scope: PermissionScope
    feedback_kind: PermissionFeedbackKind | None = Field(
        default=None, alias="feedbackKind"
    )
    permission_updates: list[PermissionUpdate] = Field(
        default_factory=list, alias="permissionUpdates"
    )


class PermissionDecision(BaseModel):
    """Canonical permission result shared by streaming and approval clients."""

    model_config = ConfigDict(populate_by_name=True)

    behavior: CommandDecision
    reason: str
    reason_code: str = Field(alias="reasonCode")
    risk: PermissionRisk
    actions: list[PermissionAction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PermissionMatcher(BaseModel):
    type: Literal[
        "all",
        "exact_input",
        "command_prefix",
        "path_prefix",
        "destination",
    ]
    value: Any = None


class PermissionRule(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(default_factory=lambda: str(uuid4()))
    tool: str
    behavior: CommandDecision
    matcher: PermissionMatcher = Field(
        default_factory=lambda: PermissionMatcher(type="all")
    )
    source: Literal["builtin", "global", "session", "runtime"] = "session"
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="createdAt"
    )
    description: str | None = None


class ToolPermissionPolicy(BaseModel):
    enabled: bool = False
    mode: PermissionMode = PermissionMode.FULL_APPROVAL
    default_action: CommandDecision = CommandDecision.ASK
    command_rules: list[dict[str, Any]] = Field(default_factory=list)


class PermissionsConfig(BaseModel):
    tools: dict[str, ToolPermissionPolicy] = Field(default_factory=dict)
