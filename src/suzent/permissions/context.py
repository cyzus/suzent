from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from suzent.permissions.models import PermissionMode
from suzent.permissions.rules import parse_rules


@dataclass(frozen=True)
class PermissionContext:
    chat_id: str
    mode: PermissionMode
    interaction_profile: str
    tool_approval_policy: dict[str, str]
    tool_permission_policies: dict[str, dict[str, Any]]
    path_resolver: Any
    sandbox_enabled: bool
    transcript: list[Any]
    permission_rules: list[Any]

    @classmethod
    def from_deps(cls, deps: Any) -> "PermissionContext":
        return cls(
            chat_id=str(getattr(deps, "chat_id", "") or ""),
            mode=parse_permission_mode(getattr(deps, "permission_mode", None)),
            interaction_profile=str(
                getattr(deps, "interaction_profile", "interactive") or "interactive"
            ),
            tool_approval_policy=dict(getattr(deps, "tool_approval_policy", {}) or {}),
            tool_permission_policies=dict(
                getattr(deps, "tool_permission_policies", {}) or {}
            ),
            path_resolver=getattr(deps, "path_resolver", None),
            sandbox_enabled=bool(getattr(deps, "sandbox_enabled", False)),
            transcript=list(getattr(deps, "last_messages", None) or []),
            permission_rules=parse_rules(getattr(deps, "permission_rules", None) or []),
        )


def parse_permission_mode(value: Any) -> PermissionMode:
    normalized = str(value or "").strip().lower()
    aliases = {
        "": PermissionMode.DEFAULT,
        "full_approval": PermissionMode.DEFAULT,
        "ask": PermissionMode.DEFAULT,
        "ask_before_edits": PermissionMode.DEFAULT,
        "accept_edits": PermissionMode.ACCEPT_EDITS,
        "full_access": PermissionMode.FULL_ACCESS,
        "plan": PermissionMode.PLAN,
        "auto": PermissionMode.AUTO,
        "strict_readonly": PermissionMode.STRICT_READONLY,
    }
    return aliases.get(normalized, PermissionMode.DEFAULT)
