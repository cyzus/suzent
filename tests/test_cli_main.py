"""Unit tests for CLI process control helpers."""

import importlib
import subprocess

import pytest
import typer
from typer.testing import CliRunner

cli_main = importlib.import_module("suzent.cli.main")
runner = CliRunner()


class _DummyProcess:
    """Simple process double for shutdown behavior tests."""

    def __init__(self):
        self._running = True
        self.signal_calls = []
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0
        self.raise_on_signal = False
        self.raise_on_terminate = False

    def poll(self):
        return None if self._running else 0

    def send_signal(self, sig):
        self.signal_calls.append(sig)
        if self.raise_on_signal:
            raise RuntimeError("signal failed")
        self._running = False

    def wait(self, timeout=None):
        self.wait_calls += 1
        if self._running:
            raise subprocess.TimeoutExpired(cmd="dummy", timeout=timeout or 0)
        return 0

    def terminate(self):
        self.terminate_calls += 1
        if self.raise_on_terminate:
            raise RuntimeError("terminate failed")
        self._running = False

    def kill(self):
        self.kill_calls += 1
        self._running = False


@pytest.mark.parametrize("is_windows", [False, True])
def test_terminate_process_noop_for_exited(monkeypatch, is_windows):
    process = _DummyProcess()
    process._running = False

    monkeypatch.setattr(cli_main, "IS_WINDOWS", is_windows)

    cli_main._terminate_process_gracefully(process)

    assert process.signal_calls == []
    assert process.terminate_calls == 0
    assert process.kill_calls == 0


def test_terminate_process_graceful_signal(monkeypatch):
    process = _DummyProcess()
    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)

    cli_main._terminate_process_gracefully(process)

    assert process.signal_calls == [cli_main.signal.SIGINT]
    assert process.terminate_calls == 0
    assert process.kill_calls == 0


def test_terminate_process_fallback_to_terminate(monkeypatch):
    process = _DummyProcess()
    process.raise_on_signal = True
    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)

    cli_main._terminate_process_gracefully(process)

    assert process.signal_calls == [cli_main.signal.SIGINT]
    assert process.terminate_calls == 1
    assert process.kill_calls == 0


def test_terminate_process_fallback_to_kill(monkeypatch):
    process = _DummyProcess()
    process.raise_on_signal = True
    process.raise_on_terminate = True
    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)

    cli_main._terminate_process_gracefully(process)

    assert process.signal_calls == [cli_main.signal.SIGINT]
    assert process.terminate_calls == 1
    assert process.kill_calls == 1


class _ServeProcessSuccess:
    """Process double that exits successfully."""

    def __init__(self):
        self.wait_calls = 0

    def wait(self):
        self.wait_calls += 1
        return 0


class _ServeProcessKeyboardInterrupt:
    """Process double that simulates Ctrl+C during wait."""

    def wait(self):
        raise KeyboardInterrupt()


def test_serve_uses_default_windows_process_group(monkeypatch):
    """Regression: `suzent serve` should not create a new process group on Windows."""
    app = typer.Typer()
    cli_main.register_commands(app)

    popen_calls = {}

    def fake_popen(cmd, env=None, **kwargs):
        popen_calls["cmd"] = cmd
        popen_calls["env"] = env
        popen_calls["kwargs"] = kwargs
        return _ServeProcessSuccess()

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)

    result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "25314"])

    assert result.exit_code == 0
    assert popen_calls["cmd"][:3] == [cli_main.sys.executable, "-m", "suzent.server"]
    assert popen_calls["env"]["SUZENT_HOST"] == "127.0.0.1"
    assert popen_calls["env"]["SUZENT_PORT"] == "25314"
    # Important assertion: no CREATE_NEW_PROCESS_GROUP is passed.
    assert "creationflags" not in popen_calls["kwargs"]


def test_serve_ctrl_c_calls_graceful_terminator(monkeypatch):
    """Regression: Ctrl+C during `serve` must attempt child shutdown."""
    app = typer.Typer()
    cli_main.register_commands(app)

    process = _ServeProcessKeyboardInterrupt()
    terminate_calls = []

    def fake_popen(cmd, env=None, **kwargs):
        return process

    def fake_terminate(proc):
        terminate_calls.append(proc)

    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_main, "_terminate_process_gracefully", fake_terminate)

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert len(terminate_calls) == 1
    assert terminate_calls[0] is process
