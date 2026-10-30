"""Pure sync planning: turn file hashes and git diffs into a reviewable SyncPlan.

Nothing here touches the disk or git, so every rule about what is risky,
destructive or conflicting can be tested directly.
"""

from __future__ import annotations

from suzent.sync.models import SyncFileChange, SyncPlan
from suzent.sync.payload import PAYLOAD_DIR_NAME


def plan_outgoing(
    operation: str,
    current_hashes: dict[str, str],
    preview_hashes: dict[str, str],
) -> SyncPlan:
    changes: list[SyncFileChange] = []
    for path in sorted(current_hashes.keys() | preview_hashes.keys()):
        before = current_hashes.get(path)
        after = preview_hashes.get(path)
        if before == after:
            continue
        if before is None:
            change_type = "added"
        elif after is None:
            change_type = "deleted"
        else:
            change_type = "modified"
        changes.append(_make_change(path, change_type, "outgoing"))
    return finalize_plan(operation, changes)


def plan_incoming(operation: str, diff_output: str) -> SyncPlan:
    changes: list[SyncFileChange] = []
    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1].replace("\\", "/").removeprefix(f"{PAYLOAD_DIR_NAME}/")
        changes.append(
            _make_change(path, _change_type_from_name_status(status), "incoming")
        )
    return finalize_plan(operation, changes)


def merge_plans(operation: str, plans: list[SyncPlan]) -> SyncPlan:
    changes: list[SyncFileChange] = []
    warnings: list[str] = []
    for plan in plans:
        changes.extend(plan.files)
        warnings.extend(plan.warnings)
    merged = finalize_plan(operation, changes)
    merged.warnings = list(dict.fromkeys([*merged.warnings, *warnings]))
    return merged


def overlapping_paths(plan: SyncPlan) -> list[str]:
    """Paths changed both locally and on the remote since the last sync."""
    incoming = {c.path for c in plan.files if c.direction == "incoming"}
    outgoing = {c.path for c in plan.files if c.direction == "outgoing"}
    return sorted(incoming & outgoing)


def _change_type_from_name_status(status: str) -> str:
    if status.startswith("D"):
        return "deleted"
    if status.startswith("A"):
        return "added"
    return "modified"


def _make_change(path: str, change_type: str, direction: str) -> SyncFileChange:
    category = _sync_category(path)
    risk = _risk_for_change(path, category, change_type)
    return SyncFileChange(
        path=path,
        category=category,
        change_type=change_type,
        risk=risk,
        direction=direction,
    )


def _sync_category(path: str) -> str:
    if path.startswith("config/"):
        return "config"
    if path.startswith("skills/"):
        return "skills"
    if path.startswith("memory/"):
        return "memory"
    return "other"


def _risk_for_change(path: str, category: str, change_type: str) -> str:
    if category == "memory" and change_type == "deleted":
        return "high"
    if category == "memory" and path in {
        "memory/MEMORY.md",
        "memory/persona.md",
        "memory/user.md",
    }:
        return "high"
    if change_type == "deleted":
        return "medium"
    return "low"


def finalize_plan(operation: str, changes: list[SyncFileChange]) -> SyncPlan:
    summary = {"added": 0, "modified": 0, "deleted": 0, "high_risk": 0}
    for change in changes:
        summary[change.change_type] += 1
        if change.risk == "high":
            summary["high_risk"] += 1

    memory_deletes = [
        change
        for change in changes
        if change.category == "memory" and change.change_type == "deleted"
    ]
    warnings: list[str] = []
    if memory_deletes:
        warnings.append(f"{len(memory_deletes)} memory file(s) would be deleted.")
    if len(memory_deletes) >= 5:
        warnings.append("Large memory deletion detected; review before syncing.")
    destructive = bool(memory_deletes or any(c.risk == "high" for c in changes))
    return SyncPlan(
        operation=operation,
        files=changes,
        summary=summary,
        destructive=destructive,
        requires_confirmation=destructive,
        warnings=warnings,
    )
