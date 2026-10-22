import os
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
from pydantic_ai import ApprovalRequired

from suzent.tools.shell.bash_tool import ShellCommandBackend
from suzent.tools.shell.shell_tools import RunCommandTool


def _ctx(tmp_path, sandbox_enabled=False):
    deps = SimpleNamespace(
        chat_id="chat-1",
        sandbox_enabled=sandbox_enabled,
        workspace_root=str(tmp_path),
        custom_volumes=[],
        path_resolver=None,
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
        description="Echo a test line",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert result.message == "Tool 'run_command' is denied by policy"


def test_accepts_command_on_host(monkeypatch, tmp_path):
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
            "-NonInteractive",
            "-Command",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; echo hi",
        ]
    else:
        assert captured["cmd"] == ["bash", "-c", "echo hi"]
    assert captured["kwargs"]["stdin"] is subprocess.DEVNULL


def test_host_output_is_published_before_command_exits(monkeypatch, tmp_path):
    tool = ShellCommandBackend()
    tool.workspace_root = str(tmp_path)
    monkeypatch.setattr(
        tool,
        "_build_cmd",
        lambda _: [
            sys.executable,
            "-c",
            "import time; print('ready', flush=True); time.sleep(0.5)",
        ],
    )
    monkeypatch.setattr(tool, "_resolve_working_dir", lambda: tmp_path)
    monkeypatch.setattr(tool, "_get_host_env", os.environ.copy)
    received = []
    started = time.monotonic()

    result = tool._execute_on_host(
        "ignored",
        timeout=3,
        output_callback=lambda stream, chunk: received.append(
            (stream, chunk, time.monotonic() - started)
        ),
    )

    assert result.success
    assert "ready" in result.message
    finished = time.monotonic() - started
    assert any(
        stream == "stdout" and "ready" in chunk and finished - elapsed > 0.25
        for stream, chunk, elapsed in received
    )


def test_run_command_yields_a_running_host_process(monkeypatch, tmp_path):
    from suzent.core.background_commands import get_background_commands
    from suzent.tools.shell.host_process_registry import HostProcessRegistry

    tool = RunCommandTool()
    monkeypatch.setattr(tool, "DEFAULT_YIELD_SECONDS", 0.2)
    monkeypatch.setattr(
        tool,
        "_build_cmd",
        lambda _: [
            sys.executable,
            "-c",
            "import time; print('ready', flush=True); time.sleep(2)",
        ],
    )
    monkeypatch.setattr(tool, "_resolve_working_dir", lambda: tmp_path)
    monkeypatch.setattr(tool, "_get_host_env", os.environ.copy)

    result = tool.forward(
        _ctx(tmp_path), content="echo ready", description="Run a slow command"
    )

    assert result.success
    assert result.metadata["background"] is True
    assert "ready" in result.message
    process_id = result.metadata["process_id"]
    assert process_id in result.message
    assert HostProcessRegistry().poll("chat-1", process_id, 0)["done"] is False

    HostProcessRegistry().kill("chat-1", process_id)
    HostProcessRegistry().evict("chat-1", process_id)
    get_background_commands().cancel("chat-1", process_id)


def test_run_command_returns_completed_host_output(monkeypatch, tmp_path):
    tool = RunCommandTool()
    monkeypatch.setattr(tool, "DEFAULT_YIELD_SECONDS", 1)
    monkeypatch.setattr(
        tool,
        "_build_cmd",
        lambda _: [sys.executable, "-c", "print('finished', flush=True)"],
    )
    monkeypatch.setattr(tool, "_resolve_working_dir", lambda: tmp_path)
    monkeypatch.setattr(tool, "_get_host_env", os.environ.copy)

    result = tool.forward(
        _ctx(tmp_path), content="echo finished", description="Run a quick command"
    )

    assert result.success
    assert result.metadata["background"] is False
    assert result.metadata["returncode"] == 0
    assert result.message == f"[cwd: {tmp_path}]\nfinished"


def test_run_command_yields_a_running_sandbox_process(monkeypatch, tmp_path):
    from suzent.core.background_commands import get_background_commands

    tool = RunCommandTool()
    monkeypatch.setattr(tool, "DEFAULT_YIELD_SECONDS", 0)
    tool._manager = SimpleNamespace(
        start_background=lambda **kwargs: "abcdef123456",
        poll_process=lambda *args: {
            "output": "sandbox ready\n",
            "offset": 14,
            "done": False,
            "exit_code": None,
        },
    )

    result = tool.forward(
        _ctx(tmp_path, sandbox_enabled=True),
        content="echo ready",
        description="Run a sandbox command",
    )

    assert result.success
    assert result.metadata["background"] is True
    assert result.metadata["process_id"] == "abcdef123456"
    assert result.metadata["next_offset"] == 14
    assert "sandbox ready" in result.message
    get_background_commands().cancel("chat-1", "abcdef123456")


def test_run_command_reports_quick_sandbox_failure(tmp_path):
    tool = RunCommandTool()
    tool._manager = SimpleNamespace(
        start_background=lambda **kwargs: "failed-command",
        poll_process=lambda *args: {
            "output": "bad input\n",
            "offset": 10,
            "done": True,
            "exit_code": 2,
        },
    )

    result = tool.forward(
        _ctx(tmp_path, sandbox_enabled=True),
        content="exit 2",
        description="Run a failing sandbox command",
    )

    assert not result.success
    assert "bad input" in result.message
    assert result.metadata["returncode"] == 2


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
            description="List files with elevated privileges",
        )
