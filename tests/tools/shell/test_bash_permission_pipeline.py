import os
from types import SimpleNamespace

import pytest
from pydantic_ai import ApprovalRequired

from suzent.config import CONFIG
from suzent.tools.shell.bash_tool import BashTool


def _ctx(tmp_path, sandbox_enabled=False):
    deps = SimpleNamespace(
        chat_id="chat-1",
        sandbox_enabled=sandbox_enabled,
        workspace_root=str(tmp_path),
        custom_volumes=[],
        path_resolver=None,
        auto_approve_tools=False,
        tool_approval_policy={},
    )
    return SimpleNamespace(deps=deps)


def test_policy_blocks_dangerous_command_when_enabled(monkeypatch, tmp_path):
    tool = BashTool()

    monkeypatch.setattr(
        CONFIG,
        "permission_policies",
        {"bash_execute": {"enabled": True, "mode": "accept_edits"}},
    )

    result = tool.forward(
        _ctx(tmp_path),
        content="sudo ls",
        description="List files with sudo",
        language="command",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert "baseline guardrails" in result.message.lower()


def test_policy_asks_unknown_command_in_full_approval(monkeypatch, tmp_path):
    tool = BashTool()

    monkeypatch.setattr(
        CONFIG,
        "permission_policies",
        {
            "bash_execute": {
                "enabled": True,
                "mode": "full_approval",
                "default_action": "ask",
            }
        },
    )

    with pytest.raises(ApprovalRequired):
        tool.forward(
            _ctx(tmp_path),
            content="echo hi",
            description="Print a test line for validation",
            language="command",
        )


def test_policy_allows_readonly_command_in_strict_mode(monkeypatch, tmp_path):
    tool = BashTool()

    class _Result:
        stdout = "ok"
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        return _Result()

    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.run", fake_run)
    monkeypatch.setattr(
        CONFIG,
        "permission_policies",
        {"bash_execute": {"enabled": True, "mode": "strict_readonly"}},
    )

    result = tool.forward(
        _ctx(tmp_path),
        content="ls",
        description="List files in working directory",
        language="command",
    )

    assert result.success
    assert "ok" in result.message
    assert result.metadata["mode"] == "host"
    if os.name == "nt":
        assert "cwd" in result.message


def test_chain_command_requires_approval_by_baseline(tmp_path):
    tool = BashTool()

    with pytest.raises(ApprovalRequired):
        tool.forward(
            _ctx(tmp_path),
            content="echo hi && echo bye",
            description="Run two chained echo commands",
            language="command",
        )


def test_git_command_requires_approval_by_baseline(tmp_path):
    tool = BashTool()

    with pytest.raises(ApprovalRequired):
        tool.forward(
            _ctx(tmp_path),
            content="git status",
            description="Check git working tree status",
            language="command",
        )
