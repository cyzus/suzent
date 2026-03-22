"""Unit tests for CLI process control helpers."""

import importlib
import subprocess

import pytest

cli_main = importlib.import_module("suzent.cli.main")


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
