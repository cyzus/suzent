"""Unit tests for CLI process control helpers."""

import importlib
import json
import subprocess
import threading
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

    pid = 4242

    def __init__(self):
        self.wait_calls = 0

    def wait(self):
        self.wait_calls += 1
        return 0


class _ServeProcessKeyboardInterrupt:
    """Process double that simulates Ctrl+C during wait."""

    def wait(self):
        raise KeyboardInterrupt()


def test_start_dev_keeps_capability_writes_local(monkeypatch, tmp_path):
    app = typer.Typer()
    cli_main.register_commands(app)

    launches = []

    def fake_popen(cmd, env=None, **kwargs):
        launches.append((cmd, env))
        return _ServeProcessSuccess()

    monkeypatch.delenv("SUZENT_CAPABILITIES_TO_REPO", raising=False)
    _stub_detached_launch(monkeypatch)
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: None)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(cli_main, "run_command", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_main, "_terminate_process_gracefully", lambda process: None)

    result = runner.invoke(app, ["start", "--dev"])

    assert result.exit_code == 0
    # Backend and frontend are both launched now, so single out the backend.
    backend_env = next(env for cmd, env in launches if "suzent.server" in cmd)
    assert "SUZENT_CAPABILITIES_TO_REPO" not in backend_env
    assert backend_env["SUZENT_DEV_MODE"] == "1"


def test_start_dev_restarts_existing_backend(monkeypatch, tmp_path):
    app = typer.Typer()
    cli_main.register_commands(app)
    killed_pids = []
    popen_calls = []

    def fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return _ServeProcessSuccess()

    _stub_detached_launch(monkeypatch)
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(
        cli_main,
        "get_pid_on_port",
        lambda port: (
            4321 if port == cli_main.DEFAULT_PORT and not killed_pids else None
        ),
    )
    monkeypatch.setattr(cli_main, "kill_process", killed_pids.append)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(cli_main, "run_command", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_main, "_terminate_process_gracefully", lambda process: None)

    result = runner.invoke(app, ["start", "--dev"])

    assert result.exit_code == 0
    assert killed_pids == [4321]
    assert popen_calls[0][:3] == [cli_main.sys.executable, "-m", "suzent.server"]
    assert "--debug" in popen_calls[0]


class _NullLog:
    """Stand-in for a detached process's log handle."""

    def write(self, _text: str) -> int:
        return 0

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


def _stub_detached_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep detached launches off the real log files and out of readiness waits.

    Without this a test would append to the user's real runtime log and then
    block for the full readiness timeout waiting for a backend that the test
    never actually started.
    """
    monkeypatch.setattr(cli_main, "_open_log", lambda name: _NullLog())
    monkeypatch.setattr(cli_main, "_record_pid", lambda name, pid: None)
    monkeypatch.setattr(cli_main, "_stop_frontend", lambda: False)
    monkeypatch.setattr(
        cli_main, "_wait_until_serving", lambda port, timeout=60.0: True
    )


def _stub_dev_start(monkeypatch, tmp_path, popen_calls):
    """Neutralize everything `start --dev` touches outside process control."""

    def fake_popen(cmd, **kwargs):
        popen_calls.append(cmd)
        return _ServeProcessSuccess()

    _stub_detached_launch(monkeypatch)
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(cli_main, "run_command", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli_main, "_terminate_process_gracefully", lambda process: None)


def test_restart_stops_running_backend_then_starts(monkeypatch, tmp_path):
    app = typer.Typer()
    cli_main.register_commands(app)
    killed_pids = []
    popen_calls = []

    _stub_dev_start(monkeypatch, tmp_path, popen_calls)
    # Running before the stop, gone once its PID has been killed.
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: not killed_pids
    )
    monkeypatch.setattr(
        cli_main, "get_pid_on_port", lambda port: None if killed_pids else 4321
    )
    monkeypatch.setattr(cli_main, "kill_process", killed_pids.append)

    result = runner.invoke(app, ["restart", "--dev"])

    assert result.exit_code == 0
    assert killed_pids == [4321]
    assert popen_calls[0][:3] == [cli_main.sys.executable, "-m", "suzent.server"]


def test_restart_forwards_custom_port_to_the_new_backend(monkeypatch, tmp_path):
    """The replacement backend must bind the port that was just stopped."""
    app = typer.Typer()
    cli_main.register_commands(app)
    killed_pids = []
    popen_calls = []
    popen_envs = []

    def fake_popen(cmd, env=None, **kwargs):
        popen_calls.append(cmd)
        popen_envs.append(env)
        return _ServeProcessSuccess()

    _stub_dev_start(monkeypatch, tmp_path, [])
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    probed_ports = []

    def fake_running(host, port, *args, **kwargs):
        probed_ports.append(port)
        return not killed_pids

    monkeypatch.setattr(cli_main, "_is_suzent_server_running", fake_running)
    monkeypatch.setattr(
        cli_main, "get_pid_on_port", lambda port: None if killed_pids else 4321
    )
    monkeypatch.setattr(cli_main, "kill_process", killed_pids.append)

    result = runner.invoke(app, ["restart", "--port", "8001", "--dev"])

    assert result.exit_code == 0
    assert probed_ports == [8001, 8001]
    assert popen_envs[0]["SUZENT_PORT"] == "8001"


def test_restart_starts_when_nothing_is_running(monkeypatch, tmp_path):
    app = typer.Typer()
    cli_main.register_commands(app)
    popen_calls = []

    _stub_dev_start(monkeypatch, tmp_path, popen_calls)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: None)
    monkeypatch.setattr(
        cli_main,
        "kill_process",
        lambda pid: pytest.fail("nothing was running, so nothing should be killed"),
    )

    result = runner.invoke(app, ["restart", "--dev"])

    assert result.exit_code == 0
    assert "No Suzent server running" in result.output
    assert popen_calls[0][:3] == [cli_main.sys.executable, "-m", "suzent.server"]


def test_restart_aborts_when_port_stays_busy(monkeypatch, tmp_path):
    app = typer.Typer()
    cli_main.register_commands(app)
    popen_calls = []

    _stub_dev_start(monkeypatch, tmp_path, popen_calls)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: True
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: 4321)
    monkeypatch.setattr(cli_main, "kill_process", lambda pid: None)
    monkeypatch.setattr(
        cli_main, "_wait_for_port_release", lambda port, timeout=2.0: False
    )

    result = runner.invoke(app, ["restart"])

    assert result.exit_code == 1
    assert "was not released" in result.output
    assert popen_calls == []


def _netstat_stub(monkeypatch: pytest.MonkeyPatch, stdout: str) -> None:
    def fake_run(
        cmd: str | list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main.subprocess, "run", fake_run)


def test_get_pid_on_port_finds_the_listening_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _netstat_stub(
        monkeypatch,
        "  TCP    127.0.0.1:1212     127.0.0.1:25314    ESTABLISHED     51296\n"
        "  TCP    0.0.0.0:25314      0.0.0.0:0          LISTENING       95696\n",
    )

    assert cli_main.get_pid_on_port(25314) == 95696


def test_get_pid_on_port_ignores_lingering_time_wait_sockets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # What a killed backend leaves behind: accepted connections draining with an
    # owning PID of 0, and no LISTENING row. The port is free.
    _netstat_stub(
        monkeypatch,
        "  TCP    127.0.0.1:25314    127.0.0.1:2112     TIME_WAIT       0\n"
        "  TCP    127.0.0.1:25314    127.0.0.1:5403     FIN_WAIT_2      0\n"
        "  TCP    100.64.50.42:2377  100.87.231.85:25314 TIME_WAIT      0\n",
    )

    assert cli_main.get_pid_on_port(25314) is None


def test_get_pid_on_port_ignores_a_listener_on_a_longer_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _netstat_stub(
        monkeypatch,
        "  TCP    0.0.0.0:125314     0.0.0.0:0          LISTENING       95696\n",
    )

    assert cli_main.get_pid_on_port(25314) is None


def test_wait_for_port_release_times_out(monkeypatch):
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: 4321)

    assert cli_main._wait_for_port_release(1234, timeout=0.0) is False


def test_stop_reports_when_no_server_is_running(monkeypatch):
    app = typer.Typer()
    cli_main.register_commands(app)

    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )

    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    assert "No Suzent server running" in result.output


def test_get_ui_binary_prefers_managed_release_over_newer_local_build(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    managed = tmp_path / "bin" / "suzent-ui.exe"
    local_build = tmp_path / "src-tauri" / "target" / "release" / "suzent.exe"
    managed.parent.mkdir(parents=True)
    local_build.parent.mkdir(parents=True)
    managed.write_bytes(b"managed")
    (managed.parent / "version.txt").write_text("v1.2.3", encoding="utf-8")
    local_build.write_bytes(b"local")
    local_build.touch()

    assert cli_main._get_ui_binary(tmp_path) == managed


@pytest.mark.parametrize(
    ("command", "expected_port"), [("start", None), ("ui", "25314")]
)
def test_release_ui_receives_workspace_directory(
    monkeypatch, tmp_path, command, expected_port
):
    app = typer.Typer()
    cli_main.register_commands(app)
    ui_binary = tmp_path / "bin" / "suzent-ui.exe"
    launched = {}

    def fake_popen(args, env=None, **kwargs):
        launched["args"] = args
        launched["env"] = env
        launched["kwargs"] = kwargs
        return _ServeProcessSuccess()

    _stub_detached_launch(monkeypatch)
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "_get_ui_binary", lambda root: ui_binary)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)

    result = runner.invoke(app, [command])

    assert result.exit_code == 0
    assert launched["args"] == [str(ui_binary)]
    assert launched["env"]["SUZENT_DIR"] == str(tmp_path)
    if expected_port is not None:
        assert launched["env"]["SUZENT_PORT"] == expected_port


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
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )

    result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "25314"])

    assert result.exit_code == 0
    assert popen_calls["cmd"][:3] == [cli_main.sys.executable, "-m", "suzent.server"]
    assert popen_calls["env"]["SUZENT_HOST"] == "127.0.0.1"
    assert popen_calls["env"]["SUZENT_PORT"] == "25314"
    assert popen_calls["env"]["SUZENT_DEV_MODE"] == "1"
    # Important assertion: no CREATE_NEW_PROCESS_GROUP is passed.
    assert "creationflags" not in popen_calls["kwargs"]


def test_serve_dev_keeps_capability_writes_local(monkeypatch):
    app = typer.Typer()
    cli_main.register_commands(app)

    popen_calls = {}

    def fake_popen(cmd, env=None, **kwargs):
        popen_calls["env"] = env
        return _ServeProcessSuccess()

    monkeypatch.delenv("SUZENT_CAPABILITIES_TO_REPO", raising=False)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )

    result = runner.invoke(app, ["serve", "--dev"])

    assert result.exit_code == 0
    assert "SUZENT_CAPABILITIES_TO_REPO" not in popen_calls["env"]


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
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )

    result = runner.invoke(app, ["serve"])

    assert result.exit_code == 0
    assert len(terminate_calls) == 1
    assert terminate_calls[0] is process


def test_update_ui_binary_records_release_version(monkeypatch):
    download_calls = []
    root = Path("C:/tmp/suzent-test-root")

    monkeypatch.setattr(cli_main, "_local_ui_version", lambda root: "")

    def fake_download(root: Path, *, version: str = "latest"):
        download_calls.append((root, version))
        return True

    monkeypatch.setattr(cli_main, "download_ui_binary", fake_download)

    assert cli_main._update_ui_binary(root, "v1.2.3")

    assert download_calls == [(root, "v1.2.3")]


def test_replace_ui_files_restores_both_files_when_metadata_install_fails(
    monkeypatch,
    tmp_path,
):
    dest = tmp_path / "suzent-ui.exe"
    version_file = tmp_path / "version.txt"
    staged_binary = tmp_path / "new-ui.exe"
    staged_version = tmp_path / "new-version.txt"
    dest.write_bytes(b"old-ui")
    version_file.write_text("v1.0.0", encoding="utf-8")
    staged_binary.write_bytes(b"new-ui")
    staged_version.write_text("v1.1.0", encoding="utf-8")
    real_replace = Path.replace

    def fail_metadata_replace(path, target):
        if path == staged_version:
            raise OSError("metadata locked")
        return real_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_metadata_replace)

    with pytest.raises(OSError, match="metadata locked"):
        cli_main._replace_ui_files(
            dest,
            version_file,
            staged_binary,
            staged_version,
        )

    assert dest.read_bytes() == b"old-ui"
    assert version_file.read_text(encoding="utf-8") == "v1.0.0"


def test_release_asset_url_pins_requested_tag():
    assert cli_main._release_asset_url("suzent.exe", "v1.2.3") == (
        "https://github.com/cyzus/suzent/releases/download/v1.2.3/suzent.exe"
    )


def test_backend_sync_args_keep_dev_extra_for_development_workspace(tmp_path):
    assert cli_main._backend_sync_args(tmp_path) == [
        "uv",
        "sync",
        "--frozen",
        "--extra",
        "social",
        "--extra",
        "dev",
    ]


def test_backend_sync_args_use_social_extra_for_bootstrapped_install(tmp_path):
    (tmp_path / ".suzent-bootstrap-complete").write_text("")

    assert cli_main._backend_sync_args(tmp_path) == [
        "uv",
        "sync",
        "--frozen",
        "--extra",
        "social",
    ]


def test_update_channel_round_trip(tmp_path):
    assert cli_main._read_update_channel(tmp_path) == "stable"

    cli_main._write_update_channel(tmp_path, "dev")

    assert cli_main._read_update_channel(tmp_path) == "dev"


def _mock_update_runtime(monkeypatch, tmp_path):
    app = typer.Typer()
    cli_main.register_commands(app)
    commands = []

    def fake_run(command, **kwargs):
        if command[:3] == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(command, 0, stdout="oldcommit\n")
        if command[:3] == ["git", "branch", "--show-current"]:
            return subprocess.CompletedProcess(command, 0, stdout="main\n")
        return subprocess.CompletedProcess(command, 0, stdout="")

    def fake_run_command(command, **kwargs):
        commands.append((command, kwargs.get("cwd")))

    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main.subprocess, "run", fake_run)
    monkeypatch.setattr(cli_main, "run_command", fake_run_command)
    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)
    return app, commands


def test_stable_update_delegates_to_release_installer(monkeypatch, tmp_path):
    (tmp_path / ".suzent-bootstrap-complete").write_text("")
    app, _commands = _mock_update_runtime(monkeypatch, tmp_path)
    delegated = []
    monkeypatch.setattr(
        cli_main,
        "_fetch_latest_release",
        lambda: {"tag_name": "v1.2.3"},
    )
    monkeypatch.setattr(
        cli_main,
        "_delegate_installer_update",
        lambda root, **kwargs: delegated.append((root, kwargs)),
    )

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert delegated == [
        (
            tmp_path,
            {"release_tag": "v1.2.3", "relaunch": None, "headless": False},
        )
    ]


def test_stable_update_accepts_headless_mode(monkeypatch, tmp_path):
    (tmp_path / ".suzent-bootstrap-complete").write_text("")
    app, _commands = _mock_update_runtime(monkeypatch, tmp_path)
    delegated = []
    monkeypatch.setattr(
        cli_main, "_fetch_latest_release", lambda: {"tag_name": "v1.2.3"}
    )
    monkeypatch.setattr(
        cli_main,
        "_delegate_installer_update",
        lambda root, **kwargs: delegated.append((root, kwargs)),
    )

    result = runner.invoke(app, ["update", "--headless"])

    assert result.exit_code == 0
    assert delegated[0][1]["headless"] is True


def test_parse_release_checksum_selects_exact_asset():
    digest = "a" * 64
    assert (
        cli_main._parse_release_checksum(
            f"{'b' * 64}  other.exe\n{digest} *suzent-installer.exe\n",
            "suzent-installer.exe",
        )
        == digest
    )


def test_plain_update_uses_dev_channel_for_source_checkout(monkeypatch, tmp_path):
    app, commands = _mock_update_runtime(monkeypatch, tmp_path)

    result = runner.invoke(app, ["update"])

    assert result.exit_code == 0
    assert "Source checkout detected" in result.stdout
    command_args = [command for command, _cwd in commands]
    assert ["git", "fetch", "origin", "main"] in command_args
    assert cli_main._read_update_channel(tmp_path) == "dev"


def test_interrupted_update_message_includes_target_and_phase(tmp_path):
    state_dir = tmp_path / ".suzent"
    state_dir.mkdir()
    (state_dir / "update-transaction.json").write_text(
        '{"target_tag":"v1.2.3","phase":"switching"}',
        encoding="utf-8",
    )

    message = cli_main._interrupted_update_message(tmp_path)

    assert message is not None
    assert "v1.2.3" in message
    assert "switching" in message
    assert "suzent repair" in message


def test_dev_update_uses_main_and_never_downloads_release_ui(monkeypatch, tmp_path):
    app, commands = _mock_update_runtime(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli_main,
        "_update_ui_binary",
        lambda *_args: pytest.fail("dev update must not install release UI"),
    )

    result = runner.invoke(app, ["update", "--dev"])

    assert result.exit_code == 0
    command_args = [command for command, _cwd in commands]
    assert ["git", "fetch", "origin", "main"] in command_args
    assert ["git", "switch", "main"] in command_args
    assert ["git", "merge", "--ff-only", "origin/main"] in command_args
    npm_ci_dirs = [cwd for command, cwd in commands if command == ["npm", "ci"]]
    assert npm_ci_dirs == [tmp_path / "frontend", tmp_path / "src-tauri"]
    assert cli_main._read_update_channel(tmp_path) == "dev"


def test_dev_update_failure_resets_branch_to_saved_commit(monkeypatch, tmp_path):
    app, commands = _mock_update_runtime(monkeypatch, tmp_path)

    def fail_first_npm_ci(command, **kwargs):
        commands.append((command, kwargs.get("cwd")))
        if command == ["npm", "ci"]:
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(cli_main, "run_command", fail_first_npm_ci)

    result = runner.invoke(app, ["update", "--dev"])

    assert result.exit_code == 1
    command_args = [command for command, _cwd in commands]
    assert ["git", "checkout", "main"] in command_args
    assert ["git", "reset", "--hard", "oldcommit"] in command_args


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


def test_windows_update_delegates_away_from_locked_launcher(monkeypatch, tmp_path):
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_bytes(b"")
    popen_calls = []

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main, "_windows_suzent_launcher_pid", lambda root: 4321)
    monkeypatch.setattr(
        cli_main.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )
    monkeypatch.delenv(cli_main._UPDATE_HELPER_ENV, raising=False)

    assert cli_main._delegate_windows_update(tmp_path, dev=True)

    command, kwargs = popen_calls[0]
    assert command[:3] == [
        str(python_exe),
        "-m",
        "suzent.cli.update_helper",
    ]
    assert command[-1] == "--dev"
    assert kwargs["env"][cli_main._UPDATE_HELPER_ENV] == "1"


def test_stable_update_launches_standalone_installer(monkeypatch, tmp_path):
    updater = tmp_path / "updater" / "suzent-installer.exe"
    updater.parent.mkdir()
    updater.write_bytes(b"")
    popen_calls = []

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main, "_install_release_updater", lambda tag: updater)
    monkeypatch.setattr(cli_main.os, "getpid", lambda: 2468)
    monkeypatch.setattr(
        cli_main.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )

    cli_main._delegate_installer_update(
        tmp_path,
        release_tag="v1.2.3",
        relaunch=tmp_path / "bin" / "suzent-ui.exe",
    )

    command, kwargs = popen_calls[0]
    assert command[:2] == [str(updater), "--update"]
    assert command[command.index("--target") + 1] == "v1.2.3"
    assert command[command.index("--wait-pid") + 1] == "2468"
    assert command[-2:] == [
        "--relaunch",
        str(tmp_path / "bin" / "suzent-ui.exe"),
    ]
    assert kwargs["cwd"] == tmp_path


def test_stable_update_uses_headless_mode_without_graphical_session(
    monkeypatch, tmp_path
):
    updater = tmp_path / "updater" / "suzent-installer"
    updater.parent.mkdir()
    updater.write_bytes(b"")
    popen_calls = []

    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)
    monkeypatch.setattr(cli_main, "_graphical_update_available", lambda: False)
    monkeypatch.setattr(cli_main, "_install_release_updater", lambda tag: updater)
    monkeypatch.setattr(
        cli_main.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )

    cli_main._delegate_installer_update(
        tmp_path,
        release_tag="v1.2.3",
        relaunch=None,
    )

    assert "--headless" in popen_calls[0][0]


def test_stable_update_falls_back_when_window_exits_immediately(monkeypatch, tmp_path):
    updater = tmp_path / "updater" / "suzent-installer.exe"
    updater.parent.mkdir()
    updater.write_bytes(b"")
    popen_calls = []

    class FailedWindow:
        def poll(self):
            return 1

    def fake_popen(command, **kwargs):
        popen_calls.append((command, kwargs))
        return FailedWindow() if len(popen_calls) == 1 else None

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main, "_graphical_update_available", lambda: True)
    monkeypatch.setattr(cli_main, "_install_release_updater", lambda tag: updater)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(cli_main.time, "sleep", lambda _seconds: None)

    cli_main._delegate_installer_update(
        tmp_path,
        release_tag="v1.2.3",
        relaunch=None,
    )

    assert "--headless" not in popen_calls[0][0]
    assert "--headless" in popen_calls[1][0]


def test_atomic_download_streams_with_progress(monkeypatch, tmp_path, capsys):
    destination = tmp_path / "asset.exe"
    observed_timeout = []

    class Response:
        headers = {"Content-Length": "6"}

        def __init__(self):
            self.chunks = iter((b"abc", b"def", b""))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return next(self.chunks)

    response = Response()

    def fake_urlopen(_request, *, timeout):
        observed_timeout.append(timeout)
        return response

    monkeypatch.setattr(cli_main.urllib.request, "urlopen", fake_urlopen)

    cli_main._download_file_atomic("https://example.test/asset", destination)

    assert destination.read_bytes() == b"abcdef"
    assert observed_timeout == [300.0]
    assert "100%" in capsys.readouterr().out


def test_windows_update_delegates_when_launcher_detection_misses(monkeypatch, tmp_path):
    python_exe = tmp_path / ".venv" / "Scripts" / "python.exe"
    python_exe.parent.mkdir(parents=True)
    python_exe.write_bytes(b"")
    popen_calls = []

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main, "_windows_suzent_launcher_pid", lambda root: None)
    monkeypatch.setattr(cli_main.os, "getpid", lambda: 9876)
    monkeypatch.setattr(
        cli_main.subprocess,
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs)),
    )
    monkeypatch.delenv(cli_main._UPDATE_HELPER_ENV, raising=False)

    assert cli_main._delegate_windows_update(tmp_path, dev=False)
    command, _kwargs = popen_calls[0]
    assert command[3:5] == ["--wait-pid", "9876"]


def test_windows_update_helper_does_not_redelegate(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setenv(cli_main._UPDATE_HELPER_ENV, "1")
    monkeypatch.setattr(
        cli_main,
        "_windows_suzent_launcher_pid",
        lambda root: pytest.fail("helper must not inspect the launcher"),
    )

    assert not cli_main._delegate_windows_update(tmp_path, dev=False)


def test_windows_launcher_detection_falls_back_to_argv(monkeypatch, tmp_path):
    launcher = tmp_path / ".venv" / "Scripts" / "suzent.exe"
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"")

    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main, "_windows_ancestor_pids", lambda: {123})
    monkeypatch.setattr(
        cli_main.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=""),
    )
    monkeypatch.setattr(cli_main.sys, "argv", [str(launcher), "update"])
    monkeypatch.setattr(cli_main.os, "getpid", lambda: 456)

    assert cli_main._windows_suzent_launcher_pid(tmp_path) == 456


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


def test_current_version_prefers_source_checkout(monkeypatch, tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "suzent"\nversion = "0.7.1"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli_main, "version", lambda _name: "0.6.6")

    assert cli_main._current_version(tmp_path) == "0.7.1"


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


def _macos_workspace(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "suzent"\nversion = "0.7.13"\n', encoding="utf-8"
    )
    icons = tmp_path / "src-tauri" / "icons"
    icons.mkdir(parents=True)
    (icons / "icon.icns").write_bytes(b"icns-payload")
    binary = tmp_path / "bin" / "suzent-ui"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"mach-o")
    return binary


def test_macos_launch_target_wraps_bare_binary_in_app_bundle(monkeypatch, tmp_path):
    """Regression: a loose executable only ever gets the generic macOS icon."""
    monkeypatch.setattr(cli_main.sys, "platform", "darwin")
    binary = _macos_workspace(tmp_path)

    launch = cli_main._macos_launch_target(tmp_path, binary)

    bundle = tmp_path / "bin" / "SUZENT.app"
    assert launch == bundle / "Contents" / "MacOS" / "suzent-ui"
    assert launch.stat().st_ino == binary.stat().st_ino
    assert (bundle / "Contents" / "Resources" / "icon.icns").read_bytes() == (
        b"icns-payload"
    )

    info = cli_main.plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "suzent-ui"
    assert info["CFBundleIconFile"] == "icon.icns"
    assert info["CFBundleIdentifier"] == "com.suzent.app"
    assert info["CFBundlePackageType"] == "APPL"
    assert info["CFBundleShortVersionString"] == "0.7.13"


def test_macos_launch_target_relinks_bundle_after_update(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main.sys, "platform", "darwin")
    binary = _macos_workspace(tmp_path)
    launch = cli_main._macos_launch_target(tmp_path, binary)

    # `suzent update` swaps the binary by rename, leaving the old inode behind.
    replacement = binary.with_name(".suzent-ui.new")
    replacement.write_bytes(b"mach-o-v2")
    replacement.replace(binary)

    assert cli_main._macos_launch_target(tmp_path, binary) == launch
    assert launch.read_bytes() == b"mach-o-v2"
    assert launch.stat().st_ino == binary.stat().st_ino


def test_macos_launch_target_skips_non_macos_platforms(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_main.sys, "platform", "linux")
    binary = _macos_workspace(tmp_path)

    assert cli_main._macos_launch_target(tmp_path, binary) == binary
    assert not (tmp_path / "bin" / "SUZENT.app").exists()


def _seed_update_cache(root: Path, latest: str, *, age_seconds: float = 0.0) -> None:
    path = cli_main._update_check_cache_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        cli_main.json.dumps(
            {
                "checked_at": cli_main.time.time() - age_seconds,
                "current_version": "0.6.2",
                "latest_version": latest,
                "html_url": "",
                "update_available": bool(latest),
                "error": "",
            }
        ),
        encoding="utf-8",
    )


def test_notify_update_never_reaches_the_network(monkeypatch, tmp_path):
    """Regression: `suzent start` used to block on GitHub whenever the cache expired."""
    _seed_update_cache(
        tmp_path, "v0.6.3", age_seconds=cli_main._UPDATE_CHECK_TTL_SECONDS * 2
    )
    monkeypatch.delenv("SUZENT_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(cli_main, "_current_version", lambda root: "0.6.2")

    def fail_fetch(timeout=None):
        raise AssertionError("startup must not fetch the release feed synchronously")

    monkeypatch.setattr(cli_main, "_fetch_latest_release", fail_fetch)
    scheduled = []
    monkeypatch.setattr(
        cli_main,
        "_refresh_update_check_cache_async",
        lambda root: scheduled.append(root),
    )

    cli_main._notify_update_available(tmp_path)

    assert scheduled == [tmp_path]


def test_notify_update_reports_a_newer_cached_release(monkeypatch, tmp_path, capsys):
    _seed_update_cache(tmp_path, "v0.6.3")
    monkeypatch.delenv("SUZENT_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(cli_main, "_current_version", lambda root: "0.6.2")
    monkeypatch.setattr(
        cli_main, "_refresh_update_check_cache_async", lambda root: None
    )

    cli_main._notify_update_available(tmp_path)

    assert "0.6.2 -> v0.6.3" in capsys.readouterr().out


def test_notify_update_stays_quiet_when_current(monkeypatch, tmp_path, capsys):
    _seed_update_cache(tmp_path, "v0.6.2")
    monkeypatch.delenv("SUZENT_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.setattr(cli_main, "_current_version", lambda root: "0.6.2")

    cli_main._notify_update_available(tmp_path)

    assert capsys.readouterr().out == ""


def test_notify_update_honors_the_skip_switch(monkeypatch, tmp_path):
    monkeypatch.setenv("SUZENT_SKIP_UPDATE_CHECK", "1")

    def fail_read(root):
        raise AssertionError("skipped check must not touch the cache")

    monkeypatch.setattr(cli_main, "_read_update_check_cache", fail_read)

    cli_main._notify_update_available(tmp_path)


def test_background_refresh_runs_detached_and_bypasses_the_cache(monkeypatch, tmp_path):
    started = {}

    class _ImmediateThread:
        def __init__(self, target, name=None, daemon=False):
            self._target = target
            started["name"] = name
            started["daemon"] = daemon

        def start(self):
            self._target()

    monkeypatch.setattr(cli_main.threading, "Thread", _ImmediateThread)
    calls = []
    monkeypatch.setattr(
        cli_main,
        "_check_for_update",
        lambda root, use_cache=True: calls.append(use_cache),
    )

    cli_main._refresh_update_check_cache_async(tmp_path)

    assert calls == [False]
    assert started["daemon"] is True


def test_update_check_cache_write_is_atomic(tmp_path):
    cli_main._write_update_check_cache(tmp_path, {"checked_at": cli_main.time.time()})

    cache_dir = cli_main._update_check_cache_path(tmp_path).parent
    assert [p.name for p in cache_dir.iterdir()] == ["update-check.json"]
    assert cli_main._read_update_check_cache(tmp_path) is not None


def test_concurrent_cache_writers_do_not_share_a_temporary_file(tmp_path):
    """Overlapping `suzent` processes can refresh the same stale cache."""
    barrier = threading.Barrier(4)
    now = cli_main.time.time()

    def _write(index: int) -> None:
        barrier.wait()
        cli_main._write_update_check_cache(
            tmp_path, {"checked_at": now, "latest_version": f"v0.6.{index}"}
        )

    threads = [threading.Thread(target=_write, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    cache_dir = cli_main._update_check_cache_path(tmp_path).parent
    assert [p.name for p in cache_dir.iterdir()] == ["update-check.json"]

    cached = cli_main._read_update_check_cache(tmp_path)
    assert cached is not None
    assert cached["latest_version"] in {f"v0.6.{i}" for i in range(4)}


@pytest.mark.skipif(
    not hasattr(subprocess, "DETACHED_PROCESS"),
    reason="DETACHED_PROCESS only exists on Windows",
)
def test_launch_detached_logs_to_a_file_and_detaches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A detached child writes to its log and is cut loose from this console."""
    captured: dict = {}

    def fake_popen(cmd: list[str], **kwargs: object) -> _ServeProcessSuccess:
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        kwargs["stdout"].write("hello from the child\n")  # type: ignore[union-attr]
        return _ServeProcessSuccess()

    monkeypatch.setattr(cli_main, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(cli_main, "IS_WINDOWS", True)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)

    cli_main._launch_detached(["sleep", "1"], log_name="backend")

    kwargs = captured["kwargs"]
    assert kwargs["stdin"] is cli_main.subprocess.DEVNULL
    assert kwargs["stdout"] is kwargs["stderr"]
    assert kwargs["creationflags"] & cli_main.subprocess.DETACHED_PROCESS
    assert "hello from the child" in (tmp_path / "runtime" / "backend.log").read_text(
        encoding="utf-8"
    )


def test_launch_detached_starts_a_new_session_on_posix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict = {}

    def fake_popen(cmd: list[str], **kwargs: object) -> _ServeProcessSuccess:
        captured["kwargs"] = kwargs
        return _ServeProcessSuccess()

    monkeypatch.setattr(cli_main, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(cli_main, "IS_WINDOWS", False)
    monkeypatch.setattr(cli_main.subprocess, "Popen", fake_popen)

    cli_main._launch_detached(["sleep", "1"], log_name="backend")

    assert captured["kwargs"]["start_new_session"] is True
    assert "creationflags" not in captured["kwargs"]


def test_start_dev_detaches_both_processes_and_reports_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Regression: the frontend exiting must no longer take the backend down.

    `start --dev` used to block on `npm run dev` and kill the backend in a
    `finally`, so any Tauri hiccup stopped a perfectly healthy server.
    """
    app = typer.Typer()
    cli_main.register_commands(app)
    launched: list[list[str]] = []
    terminated: list[object] = []

    monkeypatch.setattr(
        cli_main,
        "_launch_detached",
        lambda cmd, **kwargs: launched.append(cmd),
    )
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: None)
    monkeypatch.setattr(
        cli_main, "_wait_until_serving", lambda port, timeout=60.0: True
    )
    monkeypatch.setattr(cli_main, "_terminate_process_gracefully", terminated.append)

    result = runner.invoke(app, ["start", "--dev"])

    assert result.exit_code == 0
    assert len(launched) == 2
    assert "suzent.server" in launched[0]
    assert launched[1][-2:] == ["run", "dev"]
    assert terminated == []
    assert "Suzent is running at http://127.0.0.1" in result.output
    assert "suzent logs" in result.output


def test_start_dev_warns_when_the_backend_never_answers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = typer.Typer()
    cli_main.register_commands(app)

    monkeypatch.setattr(cli_main, "_launch_detached", lambda cmd, **kwargs: None)
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: None)
    monkeypatch.setattr(
        cli_main, "_wait_until_serving", lambda port, timeout=60.0: False
    )

    result = runner.invoke(app, ["start", "--dev"])

    assert result.exit_code == 0
    assert "No backend answered" in result.output


class _FakePsutilProcess:
    """psutil.Process double for the recorded-PID tests."""

    def __init__(self, pid: int, created: float, children: list | None = None) -> None:
        self.pid = pid
        self._created = created
        self._children = children or []
        self.killed = False

    def create_time(self) -> float:
        return self._created

    def children(self, recursive: bool = False) -> list:
        return list(self._children)

    def kill(self) -> None:
        self.killed = True


def _record_frontend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, process: _FakePsutilProcess
) -> None:
    """Write the pid record `_stop_frontend` reads, for `process`."""
    runtime = tmp_path / "runtime"
    runtime.mkdir(exist_ok=True)
    monkeypatch.setattr(cli_main, "RUNTIME_DIR", runtime)
    (runtime / "frontend.pid").write_text(
        json.dumps({"pid": process.pid, "created_at": process.create_time()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli_main.psutil, "Process", lambda pid: process if pid == process.pid else None
    )
    monkeypatch.setattr(cli_main.psutil, "wait_procs", lambda procs, timeout=None: None)


def test_stop_ends_the_recorded_dev_frontend_and_its_children(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = typer.Typer()
    cli_main.register_commands(app)
    vite = _FakePsutilProcess(5556, 1000.0)
    launcher = _FakePsutilProcess(5555, 1000.0, children=[vite])
    _record_frontend(monkeypatch, tmp_path, launcher)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )

    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    # `npm run dev` only launches; its children are what hold the port.
    assert launcher.killed and vite.killed
    assert "Dev frontend stopped" in result.output
    assert "No Suzent server running" not in result.output
    assert not (tmp_path / "runtime" / "frontend.pid").exists()


def test_stop_leaves_an_unrelated_process_on_the_frontend_port_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Holding port 18080 is not proof that Suzent started it."""
    app = typer.Typer()
    cli_main.register_commands(app)
    killed: list[int] = []
    monkeypatch.setattr(cli_main, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: 9999)
    monkeypatch.setattr(cli_main, "kill_process", killed.append)

    result = runner.invoke(app, ["stop"])

    assert result.exit_code == 0
    assert killed == []
    assert "No Suzent server running" in result.output


def test_recorded_process_rejects_a_recycled_pid(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    stranger = _FakePsutilProcess(5555, 9999.0)
    _record_frontend(monkeypatch, tmp_path, _FakePsutilProcess(5555, 1000.0))
    monkeypatch.setattr(cli_main.psutil, "Process", lambda pid: stranger)

    assert cli_main._recorded_process("frontend") is None


def test_launch_detached_records_the_pid_it_started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cli_main, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(cli_main, "_open_log", lambda name: _NullLog())
    monkeypatch.setattr(
        cli_main.subprocess, "Popen", lambda cmd, **kwargs: _ServeProcessSuccess()
    )
    monkeypatch.setattr(
        cli_main.psutil, "Process", lambda pid: _FakePsutilProcess(pid, 1000.0)
    )

    cli_main._launch_detached(["sleep", "1"], log_name="frontend")

    record = json.loads(
        (tmp_path / "runtime" / "frontend.pid").read_text(encoding="utf-8")
    )
    assert record == {"pid": _ServeProcessSuccess.pid, "created_at": 1000.0}


def test_restart_stops_the_dev_frontend_before_starting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: a leftover frontend made `restart` stop and ask about port 18080."""
    app = typer.Typer()
    cli_main.register_commands(app)
    calls: list[str] = []

    monkeypatch.setattr(cli_main, "_stop_backend", lambda port: False)
    monkeypatch.setattr(
        cli_main, "_stop_frontend", lambda: calls.append("frontend") is None
    )
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_project_root", lambda: Path("."))
    monkeypatch.setattr(
        cli_main, "_notify_update_available", lambda root: calls.append("start")
    )
    monkeypatch.setattr(cli_main, "_get_ui_binary", lambda root: None)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: None)
    monkeypatch.setattr(cli_main, "_launch_detached", lambda cmd, **kwargs: None)
    monkeypatch.setattr(
        cli_main, "_wait_until_serving", lambda port, timeout=60.0: True
    )

    result = runner.invoke(app, ["restart", "--dev"])

    assert result.exit_code == 0
    assert calls == ["frontend", "start"]


def test_logs_prints_the_tail_of_the_requested_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = typer.Typer()
    cli_main.register_commands(app)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "frontend.log").write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(cli_main, "RUNTIME_DIR", runtime)

    result = runner.invoke(app, ["logs", "--frontend", "-n", "2"])

    assert result.exit_code == 0
    assert "one" not in result.output
    assert "two" in result.output and "three" in result.output


def test_logs_explains_when_nothing_has_been_written_yet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = typer.Typer()
    cli_main.register_commands(app)
    monkeypatch.setattr(cli_main, "RUNTIME_DIR", tmp_path / "runtime")

    result = runner.invoke(app, ["logs"])

    assert result.exit_code == 1
    assert "No backend log yet" in result.output


def test_server_probe_retries_before_declaring_the_server_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loaded backend can miss one probe; `attempts` keeps it from being killed."""
    attempts: list[int] = []

    class _Response:
        status = 200

        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"app": "suzent", "status": "ok"}'

    def fake_urlopen(url: str, timeout: float = 1.0) -> _Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise OSError("timed out")
        return _Response()

    monkeypatch.setattr(cli_main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(cli_main.urllib.request, "urlopen", fake_urlopen)

    assert not cli_main._is_suzent_server_running("127.0.0.1", 25314)
    attempts.clear()
    assert cli_main._is_suzent_server_running("127.0.0.1", 25314, attempts=3)


@pytest.mark.parametrize(
    ("args", "expected_hint"),
    [
        (["start"], "suzent logs --desktop -f"),
        (["start", "--dev"], "suzent logs --frontend -f"),
    ],
)
def test_start_points_at_the_log_a_failure_would_land_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, args: list[str], expected_hint: str
) -> None:
    """The packaged app logs to desktop.log, the dev pair to frontend.log."""
    app = typer.Typer()
    cli_main.register_commands(app)
    ui_binary = tmp_path / "bin" / "suzent-ui.exe"

    _stub_detached_launch(monkeypatch)
    monkeypatch.setattr(cli_main, "_launch_detached", lambda cmd, **kwargs: None)
    monkeypatch.setattr(cli_main, "get_project_root", lambda: tmp_path)
    monkeypatch.setattr(cli_main, "_notify_update_available", lambda root: None)
    monkeypatch.setattr(cli_main, "_get_ui_binary", lambda root: ui_binary)
    monkeypatch.setattr(cli_main, "ensure_cargo_in_path", lambda: None)
    monkeypatch.setattr(cli_main, "ensure_msvc_linker", lambda: None)
    monkeypatch.setattr(cli_main, "_ensure_npm_deps", lambda root: None)
    monkeypatch.setattr(
        cli_main, "_is_suzent_server_running", lambda *args, **kwargs: False
    )
    monkeypatch.setattr(cli_main, "get_pid_on_port", lambda port: None)

    result = runner.invoke(app, args)

    assert result.exit_code == 0
    assert expected_hint in result.output
