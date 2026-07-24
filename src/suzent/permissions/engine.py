from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from suzent.permissions.actions import build_approval_decision
from suzent.permissions.auto import AutoPermissionClassifier
from suzent.permissions.auto.denial_tracker import (
    record_allowed,
)
from suzent.permissions.context import PermissionContext
from suzent.permissions.models import (
    CommandDecision,
    PermissionDecision,
    PermissionMode,
    PermissionRisk,
)
from suzent.permissions.rules import find_rule


FILESYSTEM_WRITE_TOOLS = frozenset({"write_file", "edit_file"})
SHELL_TOOLS = frozenset({"bash_execute", "BashTool"})
PROCESS_TOOL = "process_manage"
SOCIAL_TOOL = "social_message"


@dataclass(frozen=True)
class ToolPermissionRequest:
    tool_name: str
    args: dict[str, Any]
    tool_call_id: str = ""


class PermissionEngine:
    """Central policy evaluator for deferred tool calls."""

    def __init__(self, classifier: AutoPermissionClassifier | None = None) -> None:
        self.classifier = classifier or AutoPermissionClassifier()

    async def evaluate(
        self,
        request: ToolPermissionRequest,
        context: PermissionContext,
    ) -> PermissionDecision:
        deny_rule = find_rule(
            context.permission_rules,
            request.tool_name,
            request.args,
            CommandDecision.DENY,
        )
        if deny_rule is not None:
            return _decision(
                CommandDecision.DENY,
                deny_rule.description or "Action denied by a permission rule",
                "normalized_rule_deny",
                PermissionRisk.HIGH,
                metadata={"rule_id": deny_rule.id},
            )
        policy = context.tool_approval_policy.get(request.tool_name)
        if policy == "always_deny":
            return _decision(
                CommandDecision.DENY,
                "Tool denied by an explicit permission rule",
                "explicit_tool_deny",
                PermissionRisk.HIGH,
            )

        if context.mode == PermissionMode.PLAN:
            mode_decision = self._evaluate_plan_mode(request, context)
            if mode_decision.behavior == CommandDecision.DENY:
                return mode_decision
            ask_decision = self._evaluate_ask_rule(request, context)
            return ask_decision or mode_decision

        if context.mode == PermissionMode.STRICT_READONLY:
            if not self._is_readonly_operation(request):
                return _decision(
                    CommandDecision.DENY,
                    "This action is unavailable in strict read-only mode",
                    "strict_readonly",
                    PermissionRisk.HIGH,
                )
            ask_decision = self._evaluate_ask_rule(request, context)
            if ask_decision is not None:
                return ask_decision
            return _decision(
                CommandDecision.ALLOW,
                "Read-only tool operation",
                "readonly_operation",
                PermissionRisk.SAFE,
            )

        if context.mode != PermissionMode.FULL_ACCESS:
            ask_decision = self._evaluate_ask_rule(request, context)
            if ask_decision is not None:
                return ask_decision

        if request.tool_name in SHELL_TOOLS:
            decision = self._evaluate_shell(request, context)
        elif request.tool_name in FILESYSTEM_WRITE_TOOLS:
            decision = self._evaluate_filesystem_write(request, context)
        elif self._is_readonly_operation(request):
            decision = _decision(
                CommandDecision.ALLOW,
                "Read-only tool operation",
                "readonly_operation",
                PermissionRisk.SAFE,
            )
        else:
            decision = build_approval_decision(
                request.tool_name,
                request.args,
                reason="This tool can change external or persistent state",
                reason_code="tool_requires_approval",
            )

        if (
            context.mode == PermissionMode.FULL_ACCESS
            and decision.behavior == CommandDecision.ASK
        ):
            return _decision(
                CommandDecision.ALLOW,
                "Action allowed by Full Access mode",
                "mode_full_access",
                PermissionRisk.LOW,
            )
        if decision.behavior == CommandDecision.ASK and policy == "always_allow":
            return _decision(
                CommandDecision.ALLOW,
                "Tool allowed by an explicit permission rule",
                "explicit_tool_allow",
                PermissionRisk.LOW,
            )
        allow_rule = find_rule(
            context.permission_rules,
            request.tool_name,
            request.args,
            CommandDecision.ALLOW,
        )
        if decision.behavior == CommandDecision.ASK and allow_rule is not None:
            return _decision(
                CommandDecision.ALLOW,
                allow_rule.description or "Action allowed by a permission rule",
                "normalized_rule_allow",
                PermissionRisk.LOW,
                metadata={"rule_id": allow_rule.id},
            )
        if (
            context.mode == PermissionMode.AUTO
            and decision.behavior == CommandDecision.ASK
            and decision.reason_code != "shell_policy_high_risk"
        ):
            return await self._evaluate_auto(request, context, decision)
        return decision

    @staticmethod
    def _evaluate_ask_rule(
        request: ToolPermissionRequest,
        context: PermissionContext,
    ) -> PermissionDecision | None:
        ask_rule = find_rule(
            context.permission_rules,
            request.tool_name,
            request.args,
            CommandDecision.ASK,
        )
        if ask_rule is None:
            return None
        return build_approval_decision(
            request.tool_name,
            request.args,
            reason=ask_rule.description or "A permission rule requires approval",
            reason_code="normalized_rule_ask",
        )

    async def _evaluate_auto(
        self,
        request: ToolPermissionRequest,
        context: PermissionContext,
        fallback: PermissionDecision,
    ) -> PermissionDecision:
        try:
            result = await self.classifier.classify(
                tool_name=request.tool_name,
                args=request.args,
                transcript=context.transcript,
            )
        except Exception as exc:
            if context.interaction_profile == "interactive":
                payload = fallback.model_dump(by_alias=True)
                payload.update(
                    {
                        "reason": f"Auto classifier unavailable: {exc}",
                        "reasonCode": "auto_classifier_unavailable",
                    }
                )
                return PermissionDecision.model_validate(payload)
            return _decision(
                CommandDecision.DENY,
                "Auto classifier unavailable in a headless run",
                "auto_classifier_unavailable",
                PermissionRisk.HIGH,
            )

        if not result.should_block and result.confidence != "low":
            record_allowed(context.chat_id)
            return _decision(
                CommandDecision.ALLOW,
                result.reason,
                "auto_classifier_allow",
                PermissionRisk.LOW,
                metadata={
                    "confidence": result.confidence,
                    "risk_categories": result.risk_categories,
                },
            )

        if context.interaction_profile == "interactive":
            payload = fallback.model_dump(by_alias=True)
            payload.update(
                {
                    "reason": result.reason,
                    "reasonCode": "auto_classifier_high_risk",
                    "risk": PermissionRisk.HIGH.value,
                    "metadata": {
                        "confidence": result.confidence,
                        "risk_categories": result.risk_categories,
                    },
                }
            )
            return PermissionDecision.model_validate(payload)
        return _decision(
            CommandDecision.DENY,
            result.reason,
            "auto_classifier_block",
            PermissionRisk.HIGH,
            metadata={
                "confidence": result.confidence,
                "risk_categories": result.risk_categories,
            },
        )

    def _evaluate_plan_mode(
        self,
        request: ToolPermissionRequest,
        context: PermissionContext,
    ) -> PermissionDecision:
        plan_file_path = str(request.args.get("file_path") or "")
        if self._is_readonly_operation(request):
            return _decision(
                CommandDecision.ALLOW,
                "Plan mode permits this read-only operation",
                "plan_readonly_operation",
                PermissionRisk.SAFE,
            )
        if (
            request.tool_name in FILESYSTEM_WRITE_TOOLS
            and plan_file_path
            and self._is_plan_file(plan_file_path, context)
        ):
            return _decision(
                CommandDecision.ALLOW,
                "Plan mode permits editing the dedicated plan file",
                "plan_file_write",
                PermissionRisk.LOW,
            )
        return _decision(
            CommandDecision.DENY,
            "Plan mode permits read-only exploration only",
            "plan_mode_readonly",
            PermissionRisk.HIGH,
        )

    def _evaluate_filesystem_write(
        self,
        request: ToolPermissionRequest,
        context: PermissionContext,
    ) -> PermissionDecision:
        file_path = str(request.args.get("file_path") or "").strip()
        if not file_path:
            return _decision(
                CommandDecision.DENY,
                "A file path is required",
                "invalid_file_path",
                PermissionRisk.HIGH,
            )

        if context.mode == PermissionMode.FULL_ACCESS:
            return _decision(
                CommandDecision.ALLOW,
                "File writes are allowed by Full Access mode",
                "mode_full_access",
                PermissionRisk.LOW,
            )

        allowed, reason = self._is_workspace_path(file_path, context)
        if not allowed:
            return build_approval_decision(
                request.tool_name,
                request.args,
                reason=reason,
                reason_code="filesystem_write_outside_workspace",
                risk=PermissionRisk.HIGH,
            )

        if context.mode in {PermissionMode.ACCEPT_EDITS, PermissionMode.AUTO}:
            return _decision(
                CommandDecision.ALLOW,
                "Workspace edits are allowed by the current permission mode",
                "mode_accept_edits",
                PermissionRisk.LOW,
            )

        return build_approval_decision(
            request.tool_name,
            request.args,
            reason="This action will modify a file in the workspace",
            reason_code="filesystem_write",
            risk=PermissionRisk.MEDIUM,
        )

    def _evaluate_shell(
        self,
        request: ToolPermissionRequest,
        context: PermissionContext,
    ) -> PermissionDecision:
        content = str(
            request.args.get("content") or request.args.get("command") or ""
        ).strip()
        language = str(request.args.get("language") or "command")
        if not content:
            return _decision(
                CommandDecision.DENY,
                "Command content is required",
                "invalid_command",
                PermissionRisk.HIGH,
            )

        if language != "command":
            return build_approval_decision(
                request.tool_name,
                request.args,
                reason=f"Executing {language} code requires approval",
                reason_code="code_execution",
                risk=PermissionRisk.HIGH,
            )

        # Imported lazily to break the import cycle between this module
        # (reachable from suzent.permissions.__init__) and the shell-permissions
        # package, whose policy_models imports back into suzent.permissions.
        from suzent.tools.shell.permissions import evaluate_command_policy

        policy = context.tool_permission_policies.get("bash_execute", {})
        raw_rules = policy.get("command_rules", [])
        default_action = str(policy.get("default_action", "ask"))
        mode_value = self._shell_mode(context.mode, policy)
        evaluation = evaluate_command_policy(
            command_text=content,
            resolver=context.path_resolver,
            mode_value=mode_value,
            raw_rules=raw_rules if isinstance(raw_rules, list) else [],
            default_action=default_action,
        )

        if evaluation.decision == CommandDecision.ALLOW:
            return _decision(
                CommandDecision.ALLOW,
                evaluation.reason,
                "shell_policy_allow",
                PermissionRisk.LOW,
                metadata=evaluation.metadata,
            )
        if evaluation.decision == CommandDecision.DENY:
            if (
                context.mode == PermissionMode.AUTO
                and context.interaction_profile == "interactive"
            ):
                payload = build_approval_decision(
                    request.tool_name,
                    request.args,
                    reason=evaluation.reason,
                    reason_code="shell_policy_high_risk",
                    risk=PermissionRisk.CRITICAL,
                ).model_dump(by_alias=True)
                payload["metadata"] = evaluation.metadata
                return PermissionDecision.model_validate(payload)
            return _decision(
                CommandDecision.DENY,
                evaluation.reason,
                "shell_policy_deny",
                PermissionRisk.CRITICAL,
                metadata=evaluation.metadata,
            )
        return build_approval_decision(
            request.tool_name,
            request.args,
            reason=evaluation.reason,
            reason_code="shell_policy_ask",
            risk=PermissionRisk.HIGH,
        )

    @staticmethod
    def _shell_mode(mode: PermissionMode, policy: dict[str, Any]) -> str:
        if mode == PermissionMode.DEFAULT:
            return str(policy.get("mode") or "full_approval")
        if mode == PermissionMode.AUTO:
            return PermissionMode.ACCEPT_EDITS.value
        return mode.value

    @staticmethod
    def _is_workspace_path(
        file_path: str,
        context: PermissionContext,
    ) -> tuple[bool, str]:
        resolver = context.path_resolver
        if resolver is None:
            return False, "The workspace path could not be verified"
        try:
            resolved = Path(resolver.resolve(file_path)).resolve()
            workspace = Path(resolver.get_working_dir()).resolve()
            resolved.relative_to(workspace)
            return True, "Path is inside the workspace"
        except (OSError, ValueError):
            return False, "This action writes outside the approved workspace"

    @staticmethod
    def _is_plan_file(file_path: str, context: PermissionContext) -> bool:
        resolver = context.path_resolver
        if resolver is None:
            return False
        try:
            resolved = Path(resolver.resolve(file_path)).resolve()
            project_dir = Path(resolver.get_working_dir()).resolve()
            return resolved == (project_dir / "plan.md").resolve()
        except (OSError, ValueError):
            return False

    @staticmethod
    def _is_readonly_operation(request: ToolPermissionRequest) -> bool:
        if request.tool_name == PROCESS_TOOL:
            return str(request.args.get("action") or "").lower() in {
                "poll",
                "status",
            }
        if request.tool_name == SOCIAL_TOOL:
            return bool(request.args.get("list_contacts"))
        return False


def _decision(
    behavior: CommandDecision,
    reason: str,
    reason_code: str,
    risk: PermissionRisk,
    *,
    metadata: dict[str, Any] | None = None,
) -> PermissionDecision:
    return PermissionDecision(
        behavior=behavior,
        reason=reason,
        reasonCode=reason_code,
        risk=risk,
        metadata=metadata or {},
    )
