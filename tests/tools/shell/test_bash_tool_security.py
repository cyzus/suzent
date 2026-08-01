import os
import subprocess
from types import SimpleNamespace

import pytest
from pydantic_ai import ApprovalRequired

from suzent.tools.shell.bash_tool import ShellCommandBackend


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
    ctx.deps.tool_approval_policy["RunCommandTool"] = "always_deny"

    result = ShellCommandBackend().forward(
        ctx,
        content="echo hi",
        language="command",
        description="Echo a test line",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert result.message == "Tool 'run_command' is denied by policy"


def test_rejects_unsupported_language(tmp_path):
    tool = ShellCommandBackend()

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
    tool = ShellCommandBackend()

    class _Process:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            kwargs["stdout"].write(b"ok")
            kwargs["stdout"].flush()

        def wait(self, timeout=None):
            captured["timeout"] = timeout
            return self.returncode

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

    tool = ShellCommandBackend()

    class _Process:
        returncode = 0

        def __init__(self, cmd, **kwargs):
            captured["env"] = kwargs["env"]
            kwargs["stdout"].write(b"ok")
            kwargs["stdout"].flush()

        def wait(self, timeout=None):
            return self.returncode

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
    tool = ShellCommandBackend()
    killed = {"called": False}

    class _Process:
        pid = 123
        returncode = None

        def __init__(self, cmd, **kwargs):
            kwargs["stdout"].write(b"Fetching packages... 45%\n")
            kwargs["stdout"].flush()
            kwargs["stderr"].write(b"waiting for registry\n")
            kwargs["stderr"].flush()

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="slow", timeout=timeout)

    def fake_kill(process):
        killed["called"] = True
        assert process.pid == 123

    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.Popen", _Process)
    monkeypatch.setattr(
        ShellCommandBackend, "_kill_host_process_tree", staticmethod(fake_kill)
    )

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
    assert "Fetching packages... 45%" in result.message
    assert "waiting for registry" in result.message
    assert "Process timed out after 1s" in result.message
    assert "background=True" in result.message
    assert "SYSTEM REMINDER" not in result.message
    assert "Retry guidance:" in result.message
    assert result.metadata["returncode"] == 124
    assert result.metadata["stdout"] == "Fetching packages... 45%\n"
    assert result.metadata["stderr"] == "waiting for registry\n"


def test_host_timeout_bounds_captured_output(monkeypatch, tmp_path):
    tool = ShellCommandBackend()
    limit = tool.TIMEOUT_OUTPUT_BYTES_PER_STREAM

    class _Process:
        pid = 123
        returncode = None

        def __init__(self, cmd, **kwargs):
            kwargs["stdout"].write(b"a" * (limit + 100) + b"stdout-tail\n")
            kwargs["stdout"].flush()
            kwargs["stderr"].write(b"b" * (limit + 100) + b"stderr-tail\n")
            kwargs["stderr"].flush()

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="verbose", timeout=timeout)

    monkeypatch.setattr("suzent.tools.shell.bash_tool.subprocess.Popen", _Process)
    monkeypatch.setattr(
        ShellCommandBackend, "_kill_host_process_tree", staticmethod(lambda _: None)
    )

    result = tool.forward(
        _ctx(tmp_path),
        content="verbose-command",
        language="command",
        timeout=1,
        description="Run a verbose command",
    )

    stdout = result.metadata["stdout"]
    stderr = result.metadata["stderr"]
    assert stdout.startswith("a" * (limit // 3))
    assert stderr.startswith("b" * (limit // 3))
    assert "bytes omitted" in stdout
    assert "bytes omitted" in stderr
    assert stdout.endswith("stdout-tail\n")
    assert stderr.endswith("stderr-tail\n")
    assert len(stdout.encode()) <= limit + 40
    assert len(stderr.encode()) <= limit + 40
    assert "Process timed out after 1s" in result.message


def test_sandbox_timeout_result_is_classified(monkeypatch, tmp_path):
    tool = ShellCommandBackend()
    tool._manager = SimpleNamespace(
        execute=lambda **kwargs: SimpleNamespace(
            success=False,
            output="",
            error="Execution timed out after 1s",
            exit_code=124,
            timed_out=True,
        )
    )

    result = tool.forward(
        _ctx(tmp_path, sandbox_enabled=True),
        content="sleep 10",
        language="command",
        timeout=1,
        description="Run a slow sandbox command",
    )

    assert not result.success
    assert result.error_code.value == "timeout"
    assert result.metadata["returncode"] == 124
    assert "Execution timed out after 1s" in result.message
    assert "background=True" in result.message
    assert "SYSTEM REMINDER" not in result.message
    assert "Retry guidance:" in result.message


def test_sandbox_timeout_exception_uses_hidden_system_reminder(monkeypatch, tmp_path):
    def raise_timeout(**kwargs):
        raise TimeoutError("Execution timed out after 1s")

    tool = ShellCommandBackend()
    tool._manager = SimpleNamespace(execute=raise_timeout)

    result = tool.forward(
        _ctx(tmp_path, sandbox_enabled=True),
        content="sleep 10",
        language="command",
        timeout=1,
        description="Run a slow sandbox command",
    )

    assert not result.success
    assert result.error_code.value == "timeout"
    assert "SYSTEM REMINDER" not in result.message
    assert "Retry guidance:" in result.message
    assert "background=True" in result.message


def test_sandbox_exit_code_124_is_not_assumed_to_be_timeout(monkeypatch, tmp_path):
    tool = ShellCommandBackend()
    tool._manager = SimpleNamespace(
        execute=lambda **kwargs: SimpleNamespace(
            success=False,
            output="",
            error="Command exited with status 124",
            exit_code=124,
            timed_out=False,
        )
    )

    result = tool.forward(
        _ctx(tmp_path, sandbox_enabled=True),
        content="exit 124",
        language="command",
        timeout=1,
        description="Exit with status 124",
    )

    assert not result.success
    assert result.error_code.value == "execution_failed"
    assert "SYSTEM REMINDER" not in result.message


def test_default_timeout_uses_environment_override(monkeypatch):
    monkeypatch.setenv("SUZENT_SHELL_TIMEOUT_MS", "2501")

    assert ShellCommandBackend.default_timeout_seconds() == 3


def test_default_timeout_ignores_invalid_environment_override(monkeypatch):
    monkeypatch.setenv("SUZENT_SHELL_TIMEOUT_MS", "not-a-number")

    assert (
        ShellCommandBackend.default_timeout_seconds()
        == ShellCommandBackend.DEFAULT_TIMEOUT_SECONDS
    )


def test_baseline_guardrails_require_approval_for_dangerous_command(tmp_path):
    with pytest.raises(ApprovalRequired):
        ShellCommandBackend().forward(
            _ctx(tmp_path),
            content="sudo ls",
            language="command",
            description="List files with elevated privileges",
        )
