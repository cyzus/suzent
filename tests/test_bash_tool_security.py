import os
from types import SimpleNamespace

from suzent.tools.bash_tool import BashTool


def _ctx(tmp_path, sandbox_enabled=False):
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
    ctx.deps.tool_approval_policy["bash_execute"] = "always_deny"

    result = BashTool().forward(ctx, content="echo hi", language="command")

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert result.message == "Tool 'bash_execute' is denied by policy"


def test_rejects_unsupported_language(tmp_path):
    tool = BashTool()

    result = tool.forward(_ctx(tmp_path), content="print('hi')", language="ruby")

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert result.message.startswith("Unsupported language")
    assert "python" in result.message
    assert "nodejs" in result.message
    assert "command" in result.message


def test_accepts_command_language_on_host(monkeypatch, tmp_path):
    tool = BashTool()

    class _Result:
        stdout = "ok"
        stderr = ""
        returncode = 0

    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _Result()

    monkeypatch.setattr("suzent.tools.bash_tool.subprocess.run", fake_run)

    result = tool.forward(_ctx(tmp_path), content="echo hi", language="command")

    assert result.success
    assert result.message == "ok"
    assert result.metadata["mode"] == "host"
    if os.name == "nt":
        assert captured["cmd"][0] == "powershell"
        assert captured["cmd"][1:] == [
            "-NoProfile",
            "-Command",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; echo hi",
        ]
    else:
        assert captured["cmd"] == ["bash", "-c", "echo hi"]
