from __future__ import annotations

from .policy_models import CommandClass, CommandDecision, PathUse, PermissionEvaluation


def _is_dangerous_remove_target(path_text: str) -> bool:
    p = path_text.strip().strip("\"'")
    if not p:
        return False

    normalized = p.replace("\\", "/")
    if normalized in {"/", "~", "."}:
        return True

    if len(normalized) == 2 and normalized[1] == ":":
        return True

    if len(normalized) == 3 and normalized[1] == ":" and normalized[2] == "/":
        return True

    blocked_roots = {
        "/etc",
        "/proc",
        "/sys",
        "/dev",
        "c:/windows",
        "c:/program files",
        "c:/programdata",
    }
    lowered = normalized.lower().rstrip("/")
    return lowered in blocked_roots


def validate_paths(path_uses: list[PathUse], resolver) -> PermissionEvaluation | None:
    for use in path_uses:
        if use.operation == "delete" and _is_dangerous_remove_target(use.path):
            return PermissionEvaluation(
                decision=CommandDecision.DENY,
                reason=f"Dangerous delete target blocked: {use.path}",
                command_class=CommandClass.DANGEROUS,
                metadata={"path": use.path, "operation": use.operation},
            )

        try:
            candidate = use.path.strip().strip("\"'")
            if not candidate:
                continue
            resolver.resolve(candidate)
        except ValueError as exc:
            return PermissionEvaluation(
                decision=CommandDecision.DENY,
                reason=f"Path denied by policy: {use.path}",
                command_class=CommandClass.UNKNOWN,
                metadata={
                    "path": use.path,
                    "operation": use.operation,
                    "error": str(exc),
                },
            )

    return None
