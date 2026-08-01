from importlib import import_module
from typing import Any

# Shell command parsing imports the model submodule. Keep the higher-level
# context/engine/loader exports lazy so importing the shell backend cannot loop back
# through permissions.rules while the shell parser is still initializing.
from .models import (
    BashCommandPolicyRule,
    CommandClass,
    CommandContext,
    CommandDecision,
    PermissionEvaluation,
    PermissionAction,
    PermissionDecision,
    PermissionDecisionSource,
    PermissionFeedbackKind,
    PermissionMode,
    PermissionMatcher,
    PermissionRule,
    PermissionRisk,
    PermissionScope,
    PermissionUpdate,
    PathUse,
    PermissionsConfig,
    ToolPermissionPolicy,
)

_LAZY_EXPORTS = {
    "delete_global_permission_rule": (".loader", "delete_global_permission_rule"),
    "load_permission_overrides": (".loader", "load_permission_overrides"),
    "persist_global_command_rule": (".loader", "persist_global_command_rule"),
    "persist_global_permission_rule": (".loader", "persist_global_permission_rule"),
    "PermissionContext": (".context", "PermissionContext"),
    "parse_permission_mode": (".context", "parse_permission_mode"),
    "PermissionEngine": (".engine", "PermissionEngine"),
    "ToolPermissionRequest": (".engine", "ToolPermissionRequest"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute_name = target
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "load_permission_overrides",
    "persist_global_command_rule",
    "persist_global_permission_rule",
    "delete_global_permission_rule",
    "PermissionContext",
    "parse_permission_mode",
    "PermissionEngine",
    "ToolPermissionRequest",
    "BashCommandPolicyRule",
    "CommandClass",
    "CommandContext",
    "CommandDecision",
    "PermissionEvaluation",
    "PermissionAction",
    "PermissionDecision",
    "PermissionDecisionSource",
    "PermissionFeedbackKind",
    "PermissionMode",
    "PermissionMatcher",
    "PermissionRule",
    "PermissionRisk",
    "PermissionScope",
    "PermissionUpdate",
    "PathUse",
    "PermissionsConfig",
    "ToolPermissionPolicy",
]
