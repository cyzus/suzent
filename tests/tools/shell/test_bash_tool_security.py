import os
import subprocess
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
        tool_permission_policies={},
    )
    return SimpleNamespace(deps=deps)


def test_respects_explicit_deny_policy(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.deps.tool_approval_policy["bash_execute"] = "always_deny"

    result = BashTool().forward(
        ctx,
        content="echo hi",
        language="command",
        description="Echo a test line",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert result.message == "Tool 'bash_execute' is denied by policy"


def test_rejects_unsupported_language(tmp_path):
    tool = BashTool()

    result = tool.forward(
        _ctx(tmp_path),
        content="print('hi')",
        language="ruby",
        description="Run a ruby snippet",
    )

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert result.message.startswith("Unsupported language")
    assert "python" in result.message
    assert "nodejs" in result.message
    assert "command" in result.message


def test_accepts_command_language_on_host(monkeypatch, tmp_path):
    tool = BashTool()

    class _Process:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

        def communicate(self, timeout=None):
            captured["timeout"] = timeout
            return "ok", ""

    captured = {}
    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.Popen", _Process)

    result = tool.forward(
        _ctx(tmp_path),
        content="echo hi",
        language="command",
        description="Echo a test line",
    )

    assert result.success
    assert "ok" in result.message
    assert "[cwd:" in result.message
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


def test_host_env_includes_suzent_base_url(monkeypatch, tmp_path):
    from suzent.config import CONFIG

    tool = BashTool()

    class _Process:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs["env"]

        def communicate(self, timeout=None):
            return "ok", ""

    captured = {}
    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.Popen", _Process)
    monkeypatch.setattr(CONFIG, "server_url", "http://localhost:25314/chat")

    result = tool.forward(
        _ctx(tmp_path),
        content="echo $SUZENT_BASE_URL",
        language="command",
        description="Print the Suzent base URL",
    )

    assert result.success
    assert captured["env"]["SUZENT_BASE_URL"] == "http://localhost:25314"


def test_host_timeout_kills_process_tree_and_returns_tool_error(monkeypatch, tmp_path):
    tool = BashTool()
    killed = {"called": False}

    class _Process:
        pid = 123
        returncode = None

        def __init__(self, cmd, **kwargs):
            pass

        def communicate(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="slow", timeout=timeout)

    def fake_kill(process):
        killed["called"] = True
        assert process.pid == 123

    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.Popen", _Process)
    monkeypatch.setattr(BashTool, "_kill_host_process_tree", staticmethod(fake_kill))

    result = tool.forward(
        _ctx(tmp_path),
        content='node -e "setTimeout(() => {}, 500000)"',
        language="command",
        timeout=1,
        description="Run a slow node command",
    )

    assert killed["called"]
    assert not result.success
    assert result.error_code.value == "timeout"
    assert "Command timed out after 1 seconds" in result.message
    assert "background=True" in result.message


def test_baseline_guardrails_block_dangerous_command(tmp_path):
    result = BashTool().forward(
        _ctx(tmp_path),
        content="sudo ls",
        language="command",
        description="List files with elevated privileges",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert "baseline guardrails" in result.message
