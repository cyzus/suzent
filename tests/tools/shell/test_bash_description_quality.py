from types import SimpleNamespace

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


def test_description_is_required_by_signature(tmp_path):
    tool = BashTool()

    try:
        tool.forward(_ctx(tmp_path), content="echo hi", language="command")
    except TypeError as exc:
        assert "description" in str(exc)
        return

    raise AssertionError("Expected TypeError for missing required description")


def test_accepts_required_description(monkeypatch, tmp_path):
    tool = BashTool()

    class _Result:
        stdout = "ok"
        stderr = ""
        returncode = 0

    def fake_run(cmd, **kwargs):
        return _Result()

    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.run", fake_run)

    result = tool.forward(
        _ctx(tmp_path),
        content="echo hi",
        language="command",
        description="Echo a test line",
    )

    assert result.success
    assert "ok" in result.message
