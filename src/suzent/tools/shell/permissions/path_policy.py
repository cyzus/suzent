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


def validate_dangerous_paths(
    path_uses: list[PathUse],
) -> PermissionEvaluation | None:
    """Hard deny for targets no approval should be able to authorize."""
    for use in path_uses:
        if use.operation == "delete" and _is_dangerous_remove_target(use.path):
            return PermissionEvaluation(
                decision=CommandDecision.DENY,
                reason=f"Dangerous delete target blocked: {use.path}",
                command_class=CommandClass.DANGEROUS,
                metadata={"path": use.path, "operation": use.operation},
            )
    return None


def validate_paths(path_uses: list[PathUse], resolver) -> PermissionEvaluation | None:
    """Ask before touching a path outside the chat's grants.

    This is advisory, not a boundary. Paths are only extracted for the base
    commands in the catalog, so `cat /etc/passwd` is caught while
    `python -c "open('/etc/passwd').read()"` is not — it filters command names,
    not access. Treating it as a hard deny therefore blocked the reviewable
    tools while leaving every interpreter open, and did so above the consent
    layer, where no permission rule or mode could authorize the folder the user
    had just asked the agent to work in.

    Sandbox mode is different: there the resolver backs real containment, so a
    path it rejects stays rejected.
    """
    dangerous = validate_dangerous_paths(path_uses)
    if dangerous is not None:
        return dangerous

    sandboxed = bool(getattr(resolver, "sandbox_enabled", False))

    def outside(use: PathUse, detail: str) -> PermissionEvaluation:
        return PermissionEvaluation(
            # Sandbox mode is real containment, so an unreachable path stays a
            # denial there. On the host it is a prompt the user can answer.
            decision=CommandDecision.DENY if sandboxed else CommandDecision.ASK,
            reason=f"Path is outside this chat's granted directories: {use.path}",
            command_class=CommandClass.UNKNOWN,
            metadata={"path": use.path, "operation": use.operation, "error": detail},
        )

    for use in path_uses:
        candidate = use.path.strip().strip("\"'")
        if not candidate:
            continue
        try:
            resolved = resolver.resolve(candidate)
        except ValueError as exc:
            # Unresolvable rather than merely ungranted: an unregistered mount,
            # a UNC share, a traversal out of a volume.
            return outside(use, str(exc))
        # resolve() no longer refuses ungranted host paths, so ask the resolver
        # directly instead of reading a raised error as the signal.
        if not resolver.allows(resolved):
            return outside(use, f"resolved to {resolved}")

    return None
