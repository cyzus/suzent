"""Unit tests for CLI process control helpers."""

import importlib
import subprocess
from pathlib import Path

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


def test_update_ui_binary_records_release_version(monkeypatch):
    download_calls = []
    root = Path("C:/tmp/suzent-test-root")

    monkeypatch.setattr(
        cli_main, "_fetch_latest_release", lambda: {"tag_name": "v1.2.3"}
    )
    monkeypatch.setattr(cli_main, "_local_ui_version", lambda root: "")

    def fake_download(root: Path, *, version: str = "latest"):
        download_calls.append((root, version))
        return True

    monkeypatch.setattr(cli_main, "download_ui_binary", fake_download)

    cli_main._update_ui_binary(root)

    assert download_calls == [(root, "v1.2.3")]


def test_backend_sync_args_keep_dev_extra_for_development_workspace(tmp_path):
    assert cli_main._backend_sync_args(tmp_path) == [
        "uv",
        "sync",
        "--extra",
        "social",
        "--extra",
        "dev",
    ]


def test_backend_sync_args_use_social_extra_for_bootstrapped_install(tmp_path):
    (tmp_path / ".suzent-bootstrap-complete").write_text("")

    assert cli_main._backend_sync_args(tmp_path) == ["uv", "sync", "--extra", "social"]


def test_windows_app_suzent_pids_parse_powershell_output(monkeypatch):
    def fake_run(cmd, **kwargs):
        assert cmd[:3] == ["powershell", "-NoProfile", "-Command"]
        return subprocess.CompletedProcess(
            cmd, 0, stdout="123\nnot-a-pid\n456\n", stderr=""
        )

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main.subprocess, "run", fake_run)

    assert cli_main._windows_app_suzent_pids(exclude_pids={123}) == [456]


def test_windows_suzent_backend_pids_parse_powershell_output(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        assert cmd[:3] == ["powershell", "-NoProfile", "-Command"]
        return subprocess.CompletedProcess(
            cmd, 0, stdout="111\nnot-a-pid\n222\n", stderr=""
        )

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main.subprocess, "run", fake_run)

    assert cli_main._windows_suzent_backend_pids(tmp_path, exclude_pids={111}) == [222]


@pytest.mark.parametrize(
    ("latest", "current", "expected"),
    [
        ("v0.6.3", "0.6.2", True),
        ("0.6.2", "0.6.2", False),
        ("v0.6.1", "0.6.2", False),
    ],
)
def test_is_newer_version(latest, current, expected):
    assert cli_main._is_newer_version(latest, current) is expected


def test_check_for_update_detects_new_release(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "_current_version", lambda root: "0.6.2")

    def fake_fetch_latest_release(timeout=10.0):
        return {"tag_name": "v0.6.3", "html_url": "https://example.test/release"}

    monkeypatch.setattr(cli_main, "_fetch_latest_release", fake_fetch_latest_release)

    result = cli_main._check_for_update(tmp_path, use_cache=False)

    assert result["current_version"] == "0.6.2"
    assert result["latest_version"] == "v0.6.3"
    assert result["update_available"] is True
    assert (tmp_path / ".suzent" / "update-check.json").exists()


def test_check_for_update_uses_fresh_cache(monkeypatch, tmp_path):
    cache_path = tmp_path / ".suzent" / "update-check.json"
    cache_path.parent.mkdir()
    cache_path.write_text(
        cli_main.json.dumps(
            {
                "checked_at": cli_main.time.time(),
                "latest_version": "v0.6.3",
                "html_url": "https://example.test/release",
                "update_available": True,
                "error": "",
            }
        )
    )

    monkeypatch.setattr(cli_main, "_current_version", lambda root: "0.6.2")

    def fail_fetch_latest_release(timeout=10.0):
        raise AssertionError("fresh cache should avoid network")

    monkeypatch.setattr(cli_main, "_fetch_latest_release", fail_fetch_latest_release)

    result = cli_main._check_for_update(tmp_path, use_cache=True)

    assert result["latest_version"] == "v0.6.3"
    assert result["current_version"] == "0.6.2"
    assert result["update_available"] is True


def test_check_update_json_command(monkeypatch):
    app = typer.Typer()
    cli_main.register_commands(app)

    monkeypatch.setattr(cli_main, "get_project_root", lambda: Path("C:/tmp/suzent"))
    monkeypatch.setattr(
        cli_main,
        "_check_for_update",
        lambda root, use_cache=False: {
            "checked_at": 1,
            "current_version": "0.6.2",
            "latest_version": "v0.6.3",
            "html_url": "https://example.test/release",
            "update_available": True,
            "error": "",
        },
    )

    result = runner.invoke(app, ["check-update", "--json"])

    assert result.exit_code == 0
    payload = cli_main.json.loads(result.output)
    assert payload["current_version"] == "0.6.2"
    assert payload["latest_version"] == "v0.6.3"
    assert payload["update_available"] is True
