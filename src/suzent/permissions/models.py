from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class PermissionMode(str, Enum):
    STRICT_READONLY = "strict_readonly"
    ACCEPT_EDITS = "accept_edits"
    FULL_APPROVAL = "full_approval"


class CommandDecision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


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


class ToolPermissionPolicy(BaseModel):
    enabled: bool = False
    mode: PermissionMode = PermissionMode.FULL_APPROVAL
    default_action: CommandDecision = CommandDecision.ASK
    command_rules: list[dict[str, Any]] = Field(default_factory=list)


class PermissionsConfig(BaseModel):
    tools: dict[str, ToolPermissionPolicy] = Field(default_factory=dict)
