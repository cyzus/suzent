from __future__ import annotations

from typing import Any

from suzent.permissions.models import (
    CommandDecision,
    PermissionAction,
    PermissionDecision,
    PermissionFeedbackKind,
    PermissionRisk,
    PermissionScope,
    PermissionUpdate,
)


def _rule_update(
    *,
    destination: str,
    tool_name: str,
    matcher: dict[str, Any],
    behavior: str,
) -> PermissionUpdate:
    return PermissionUpdate(
        type="add_rule",
        destination=destination,
        payload={
            "tool": tool_name,
            "behavior": behavior,
            "matcher": matcher,
        },
    )


def build_approval_decision(
    tool_name: str,
    args: dict[str, Any] | None,
    *,
    reason: str = "This tool call requires approval",
    reason_code: str = "tool_requires_approval",
    risk: PermissionRisk = PermissionRisk.MEDIUM,
) -> PermissionDecision:
    """Build the actions offered for a deferred tool call.

    Bash persistence is scoped to the exact command. Other tools retain the
    current tool-wide remember behavior during the migration period.
    """

    args = args or {}
    is_bash = tool_name in {"bash_execute", "BashTool"}
    is_shell_command = (
        is_bash and str(args.get("language") or "command").lower() == "command"
    )
    if is_shell_command:
        command = str(args.get("content") or args.get("command") or "").strip()
        matcher = {"type": "exact_input", "value": {"command": command}}
        session_label = "Allow this command for session"
        global_label = "Always allow this command"
    else:
        matcher = {"type": "all"}
        session_label = "Always allow for session"
        global_label = "Always allow globally"

    actions = [
        PermissionAction(
            id="allow_once",
            label="Allow",
            behavior="allow",
            scope=PermissionScope.ONCE,
        ),
    ]
    # Shell commands can be remembered safely as exact-input rules. Inline
    # Python/Node programs are intentionally one-shot: persisting an arbitrary
    # code blob is confusing and provides little reusable authority.
    if not is_bash or is_shell_command:
        actions.extend(
            [
                PermissionAction(
                    id="allow_session",
                    label=session_label,
                    behavior="allow",
                    scope=PermissionScope.SESSION,
                    permissionUpdates=[
                        _rule_update(
                            destination="session",
                            tool_name=tool_name,
                            matcher=matcher,
                            behavior="allow",
                        )
                    ],
                ),
                PermissionAction(
                    id="allow_global",
                    label=global_label,
                    behavior="allow",
                    scope=PermissionScope.GLOBAL,
                    permissionUpdates=[
                        _rule_update(
                            destination="global",
                            tool_name=tool_name,
                            matcher=matcher,
                            behavior="allow",
                        )
                    ],
                ),
            ]
        )
    actions.append(
        PermissionAction(
            id="reject",
            label="Reject",
            behavior="deny",
            scope=PermissionScope.ONCE,
            feedbackKind=PermissionFeedbackKind.REJECT,
        )
    )

    return PermissionDecision(
        behavior=CommandDecision.ASK,
        reason=reason,
        reasonCode=reason_code,
        risk=risk,
        actions=actions,
    )


def resolve_action(
    decision: dict[str, Any],
    action_id: str,
) -> tuple[bool, str]:
    """Resolve an offered action into legacy approved/remember values.

    The action must be present in the persisted backend decision. This prevents
    clients from inventing a broader scope than the backend offered.
    """

    actions = decision.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Pending approval has no available actions")

    action = next(
        (
            candidate
            for candidate in actions
            if isinstance(candidate, dict) and candidate.get("id") == action_id
        ),
        None,
    )
    if action is None:
        raise ValueError(f"Permission action was not offered: {action_id}")

    behavior = str(action.get("behavior") or "")
    if behavior not in {"allow", "deny"}:
        raise ValueError(f"Invalid permission action behavior: {behavior}")

    scope = str(action.get("scope") or "once")
    remember = scope if scope in {"session", "global"} else ""
    return behavior == "allow", remember


def get_offered_action(
    decision: dict[str, Any],
    action_id: str,
) -> dict[str, Any]:
    actions = decision.get("actions")
    if not isinstance(actions, list):
        raise ValueError("Pending approval has no available actions")
    action = next(
        (
            candidate
            for candidate in actions
            if isinstance(candidate, dict) and candidate.get("id") == action_id
        ),
        None,
    )
    if action is None:
        raise ValueError(f"Permission action was not offered: {action_id}")
    return action
