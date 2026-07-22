from __future__ import annotations

from pathlib import Path

import pytest

from suzent.permissions.context import PermissionContext
from suzent.permissions.engine import PermissionEngine, ToolPermissionRequest
from suzent.permissions.models import CommandDecision, PermissionMode
from suzent.permissions.rules import parse_rules


class Resolver:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def resolve(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path.resolve()
        return (self.workspace / path).resolve()

    def get_working_dir(self) -> Path:
        return self.workspace


def context(
    tmp_path: Path,
    *,
    mode: PermissionMode = PermissionMode.DEFAULT,
    interaction_profile: str = "interactive",
    tool_approval_policy: dict[str, str] | None = None,
    tool_permission_policies: dict | None = None,
    permission_rules: list[dict] | None = None,
) -> PermissionContext:
    return PermissionContext(
        chat_id="chat-1",
        mode=mode,
        interaction_profile=interaction_profile,
        tool_approval_policy=tool_approval_policy or {},
        tool_permission_policies=tool_permission_policies or {},
        permission_rules=parse_rules(permission_rules or []),
        path_resolver=Resolver(tmp_path),
        sandbox_enabled=False,
        transcript=[],
    )


@pytest.mark.asyncio
async def test_default_mode_asks_before_workspace_edit(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": "README.md"}),
        context(tmp_path),
    )

    assert decision.behavior == CommandDecision.ASK
    assert decision.reason_code == "filesystem_write"


@pytest.mark.asyncio
async def test_accept_edits_allows_workspace_edit(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("edit_file", {"file_path": "src/app.py"}),
        context(tmp_path, mode=PermissionMode.ACCEPT_EDITS),
    )

    assert decision.behavior == CommandDecision.ALLOW
    assert decision.reason_code == "mode_accept_edits"


@pytest.mark.asyncio
async def test_accept_edits_asks_outside_workspace(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": str(outside)}),
        context(tmp_path, mode=PermissionMode.ACCEPT_EDITS),
    )

    assert decision.behavior == CommandDecision.ASK
    assert decision.reason_code == "filesystem_write_outside_workspace"


@pytest.mark.asyncio
async def test_plan_mode_denies_normal_edit(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": "src/app.py"}),
        context(tmp_path, mode=PermissionMode.PLAN),
    )

    assert decision.behavior == CommandDecision.DENY
    assert decision.reason_code == "plan_mode_readonly"


@pytest.mark.asyncio
async def test_plan_mode_allows_dedicated_plan_file(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": "plan.md"}),
        context(tmp_path, mode=PermissionMode.PLAN),
    )

    assert decision.behavior == CommandDecision.ALLOW
    assert decision.reason_code == "plan_file_write"


@pytest.mark.asyncio
async def test_explicit_tool_deny_precedes_mode(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": "README.md"}),
        context(
            tmp_path,
            mode=PermissionMode.ACCEPT_EDITS,
            tool_approval_policy={"write_file": "always_deny"},
        ),
    )

    assert decision.behavior == CommandDecision.DENY
    assert decision.reason_code == "explicit_tool_deny"


@pytest.mark.asyncio
async def test_shell_rule_is_evaluated_by_central_engine(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest(
            "bash_execute",
            {"content": "npm test", "language": "command"},
        ),
        context(
            tmp_path,
            tool_permission_policies={
                "bash_execute": {
                    "enabled": True,
                    "mode": "full_approval",
                    "default_action": "ask",
                    "command_rules": [
                        {
                            "pattern": "npm test",
                            "match_type": "exact",
                            "action": "allow",
                        }
                    ],
                }
            },
        ),
    )

    assert decision.behavior == CommandDecision.ALLOW
    assert decision.reason_code == "shell_policy_allow"


class Classifier:
    def __init__(self, *, should_block: bool, confidence: str = "high"):
        self.should_block = should_block
        self.confidence = confidence

    async def classify(self, **kwargs):
        from suzent.permissions.auto.models import AutoClassificationResult

        return AutoClassificationResult(
            should_block=self.should_block,
            reason="classifier verdict",
            confidence=self.confidence,
            risk_categories=["test"],
        )


@pytest.mark.asyncio
async def test_auto_mode_classifies_unresolved_tool(tmp_path: Path) -> None:
    decision = await PermissionEngine(
        classifier=Classifier(should_block=False)
    ).evaluate(
        ToolPermissionRequest("social_message", {"message": "hello"}),
        context(tmp_path, mode=PermissionMode.AUTO),
    )

    assert decision.behavior == CommandDecision.ALLOW
    assert decision.reason_code == "auto_classifier_allow"


@pytest.mark.asyncio
async def test_auto_mode_prompts_for_risky_classifier_result(tmp_path: Path) -> None:
    decision = await PermissionEngine(
        classifier=Classifier(should_block=True)
    ).evaluate(
        ToolPermissionRequest("social_message", {"message": "hello"}),
        context(tmp_path, mode=PermissionMode.AUTO),
    )

    assert decision.behavior == CommandDecision.ASK
    assert decision.reason_code == "auto_classifier_high_risk"
    assert decision.risk.value == "high"


@pytest.mark.asyncio
async def test_auto_mode_headless_blocks_risky_classifier_result(
    tmp_path: Path,
) -> None:
    decision = await PermissionEngine(
        classifier=Classifier(should_block=True)
    ).evaluate(
        ToolPermissionRequest("social_message", {"message": "hello"}),
        context(
            tmp_path,
            mode=PermissionMode.AUTO,
            interaction_profile="headless",
        ),
    )

    assert decision.behavior == CommandDecision.DENY
    assert decision.reason_code == "auto_classifier_block"


@pytest.mark.asyncio
async def test_auto_mode_prompts_for_high_risk_shell_policy(
    tmp_path: Path,
) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest(
            "bash_execute",
            {"content": "chmod 777 secrets.txt", "language": "command"},
        ),
        context(tmp_path, mode=PermissionMode.AUTO),
    )

    assert decision.behavior == CommandDecision.ASK
    assert decision.reason_code == "shell_policy_high_risk"
    assert decision.risk.value == "critical"


@pytest.mark.asyncio
async def test_process_poll_is_readonly_in_plan_mode(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest(
            "process_manage",
            {"process_id": "abcdef123456", "action": "poll"},
        ),
        context(tmp_path, mode=PermissionMode.PLAN),
    )

    assert decision.behavior == CommandDecision.ALLOW
    assert decision.reason_code == "plan_readonly_operation"


@pytest.mark.asyncio
async def test_social_contact_listing_is_readonly(tmp_path: Path) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("social_message", {"list_contacts": True}),
        context(tmp_path),
    )

    assert decision.behavior == CommandDecision.ALLOW
    assert decision.reason_code == "readonly_operation"


@pytest.mark.asyncio
async def test_normalized_deny_rule_precedes_allow_rule(tmp_path: Path) -> None:
    rules = [
        {
            "tool": "write_file",
            "behavior": "allow",
            "matcher": {"type": "all"},
        },
        {
            "tool": "write_file",
            "behavior": "deny",
            "matcher": {
                "type": "path_prefix",
                "value": "secrets/",
            },
        },
    ]
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": "secrets/token.txt"}),
        context(tmp_path, permission_rules=rules),
    )

    assert decision.behavior == CommandDecision.DENY
    assert decision.reason_code == "normalized_rule_deny"


@pytest.mark.asyncio
async def test_normalized_exact_allow_only_matches_same_command(
    tmp_path: Path,
) -> None:
    rules = [
        {
            "tool": "bash_execute",
            "behavior": "allow",
            "matcher": {
                "type": "exact_input",
                "value": {"command": "npm test"},
            },
        }
    ]

    allowed = await PermissionEngine().evaluate(
        ToolPermissionRequest(
            "bash_execute",
            {"content": "npm test", "language": "command"},
        ),
        context(tmp_path, permission_rules=rules),
    )
    different = await PermissionEngine().evaluate(
        ToolPermissionRequest(
            "bash_execute",
            {"content": "npm publish", "language": "command"},
        ),
        context(tmp_path, permission_rules=rules),
    )

    assert allowed.behavior == CommandDecision.ALLOW
    assert allowed.reason_code == "normalized_rule_allow"
    assert different.behavior != CommandDecision.ALLOW


@pytest.mark.asyncio
async def test_ask_rule_cannot_bypass_plan_mode_write_denial(
    tmp_path: Path,
) -> None:
    decision = await PermissionEngine().evaluate(
        ToolPermissionRequest("write_file", {"file_path": "src/app.py"}),
        context(
            tmp_path,
            mode=PermissionMode.PLAN,
            permission_rules=[
                {
                    "tool": "write_file",
                    "behavior": "ask",
                    "matcher": {"type": "all"},
                }
            ],
        ),
    )

    assert decision.behavior == CommandDecision.DENY
    assert decision.reason_code == "plan_mode_readonly"
