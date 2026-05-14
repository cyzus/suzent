import shutil
import subprocess
from pathlib import Path

import pytest

from suzent.core.codex_session import CodexSessionService, CodexSessionStatus


def completed(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        ["codex", "login", "status"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_status_reports_not_installed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)

    status = CodexSessionService().get_status()

    assert status.status == "not_installed"
    assert status.connected is False
    assert status.executable is None


def test_status_reports_chatgpt_login(monkeypatch):
    service = CodexSessionService(executable="codex")
    monkeypatch.setattr(
        service,
        "_run",
        lambda _args, executable: completed(stderr="Logged in using ChatGPT"),
    )

    status = service.get_status()

    assert status.status == "connected"
    assert status.connected is True
    assert status.auth_mode == "chatgpt"


def test_status_rejects_api_key_login_for_subscription(monkeypatch):
    service = CodexSessionService(executable="codex")
    monkeypatch.setattr(
        service,
        "_run",
        lambda _args, executable: completed(stderr="Logged in using an API key - sk-proj-***ABCDE"),
    )

    status = service.get_status()

    assert status.status == "api_key_login"
    assert status.connected is False
    assert status.auth_mode == "api_key"


def test_status_reports_not_logged_in(monkeypatch):
    service = CodexSessionService(executable="codex")
    monkeypatch.setattr(
        service,
        "_run",
        lambda _args, executable: completed(stderr="Not logged in", returncode=1),
    )

    status = service.get_status()

    assert status.status == "not_logged_in"
    assert status.connected is False


def test_login_start_failure_does_not_expose_secrets(monkeypatch):
    service = CodexSessionService(executable="codex")

    def raise_on_popen(*_args, **_kwargs):
        raise RuntimeError("boom token=secret")

    monkeypatch.setattr(subprocess, "Popen", raise_on_popen)
    monkeypatch.setattr(
        service,
        "_run",
        lambda _args, executable: completed(stderr="Not logged in", returncode=1),
    )

    result = service.start_login()

    assert result.success is False
    assert result.message == "Failed to start Codex login."
    assert "secret" not in result.message


def test_exec_prompt_runs_codex_exec_and_reads_last_message(monkeypatch):
    service = CodexSessionService(executable="codex")
    monkeypatch.setattr(
        service,
        "get_status",
        lambda: CodexSessionStatus(
            status="connected",
            connected=True,
            auth_mode="chatgpt",
            executable="codex",
            codex_home="C:\\Users\\test\\.codex",
            message="Codex is logged in using ChatGPT.",
        ),
    )
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["input"] = kwargs["input"]
        output_path = Path(cmd[cmd.index("--output-last-message") + 1])
        output_path.write_text("hello from codex", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.exec_prompt(
        "say hello",
        model="gpt-5.5",
        cwd="C:\\repo",
        timeout_seconds=1,
    )

    assert result.success is True
    assert result.output == "hello from codex"
    assert captured["input"] == "say hello"
    assert captured["cmd"][:2] == ["codex", "exec"]
    assert "--model" in captured["cmd"]
    assert "gpt-5.5" in captured["cmd"]
    assert "--cd" in captured["cmd"]
    assert "C:\\repo" in captured["cmd"]
    assert "-c" in captured["cmd"]
    assert 'approval_policy="never"' in captured["cmd"]
    assert "--sandbox" in captured["cmd"]
    assert "read-only" in captured["cmd"]


def test_exec_prompt_requires_chatgpt_session(monkeypatch):
    service = CodexSessionService(executable="codex")
    monkeypatch.setattr(
        service,
        "get_status",
        lambda: CodexSessionStatus(
            status="api_key_login",
            connected=False,
            auth_mode="api_key",
            executable="codex",
            codex_home="C:\\Users\\test\\.codex",
            message="Codex is logged in using an API key.",
            recovery_hint="Run codex logout, then codex login.",
        ),
    )

    result = service.exec_prompt("hello")

    assert result.success is False
    assert result.message == "Run codex logout, then codex login."


def test_exec_prompt_extracts_codex_error_message(monkeypatch):
    service = CodexSessionService(executable="codex")
    monkeypatch.setattr(
        service,
        "get_status",
        lambda: CodexSessionStatus(
            status="connected",
            connected=True,
            auth_mode="chatgpt",
            executable="codex",
            codex_home="C:\\Users\\test\\.codex",
            message="Codex is logged in using ChatGPT.",
        ),
    )

    def fake_run(cmd, **_kwargs):
        stdout = (
            "OpenAI Codex v0.130.0\n"
            'ERROR: {"error":{"message":"Model is not supported."}}\n'
        )
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = service.exec_prompt("hello", model="unsupported-model")

    assert result.success is False
    assert result.message == "Model is not supported."


@pytest.mark.integration
def test_real_codex_login_status_smoke():
    if shutil.which("codex") is None:
        pytest.skip("Codex CLI is not installed on PATH")

    status = CodexSessionService().get_status()

    assert status.status in {
        "connected",
        "not_logged_in",
        "api_key_login",
        "error",
    }
    assert status.message
