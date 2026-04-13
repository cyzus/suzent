from types import SimpleNamespace

from suzent.tools.process_tool import ProcessTool


def _ctx(tmp_path, sandbox_enabled=True):
    deps = SimpleNamespace(
        chat_id="chat-1",
        sandbox_enabled=sandbox_enabled,
        workspace_root=str(tmp_path),
        custom_volumes=[],
        auto_approve_tools=False,
        tool_approval_policy={},
    )
    return SimpleNamespace(deps=deps)


def test_respects_explicit_deny_policy(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.deps.tool_approval_policy["process_manage"] = "always_deny"

    result = ProcessTool().forward(
        ctx,
        process_id="abcdef123456",
        action="status",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert result.message == "Tool 'process_manage' is denied by policy"


def test_rejects_invalid_process_id(tmp_path):
    tool = ProcessTool()

    result = tool.forward(_ctx(tmp_path), process_id="not-valid", action="poll")

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert result.message == "Invalid process_id format."


def test_rejects_negative_offset(tmp_path):
    tool = ProcessTool()

    result = tool.forward(
        _ctx(tmp_path),
        process_id="abcdef123456",
        action="poll",
        offset=-1,
    )

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert result.message == "offset must be greater than or equal to 0."


def test_rejects_unknown_action(tmp_path):
    tool = ProcessTool()

    result = tool.forward(
        _ctx(tmp_path),
        process_id="abcdef123456",
        action="delete",
    )

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert "Unknown action 'delete'" in result.message
