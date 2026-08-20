from __future__ import annotations

import plistlib

from suzent.service.platforms.linux import LinuxServiceManager
from suzent.service.platforms.macos import LABEL, MacOSServiceManager
from suzent.service.platforms import windows as windows_module
from suzent.service.platforms.windows import WindowsServiceManager


def test_linux_unit_is_user_level_and_restarts_on_failure(tmp_path, monkeypatch):
    manager = LinuxServiceManager()
    definition = tmp_path / "suzent.service"
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        LinuxServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(
        manager, "_systemctl", lambda *args, **_kwargs: calls.append(args)
    )

    manager.install()

    unit = definition.read_text(encoding="utf-8")
    assert "Restart=on-failure" in unit
    assert "TimeoutStopSec=15" in unit
    assert "suzent.service.runtime" in unit
    assert calls == [("daemon-reload",), ("enable", "suzent.service")]


def test_macos_plist_is_background_launch_agent(tmp_path, monkeypatch):
    manager = MacOSServiceManager()
    definition = tmp_path / "com.suzent.service.plist"
    monkeypatch.setattr(
        MacOSServiceManager, "definition_path", property(lambda _self: definition)
    )

    manager.install()

    with definition.open("rb") as handle:
        payload = plistlib.load(handle)
    assert payload["Label"] == LABEL
    assert payload["RunAtLoad"] is True
    assert payload["ProcessType"] == "Background"
    assert "suzent.service.runtime" in payload["ProgramArguments"]


def test_windows_service_uses_pythonw_supervisor_with_bounded_restarts(
    tmp_path, monkeypatch
):
    manager = WindowsServiceManager()
    runtime_dir = tmp_path / "Suzent Data"
    definition = runtime_dir / "service-supervisor.pyw"
    stop_request = tmp_path / "service-stop.request"
    autostart: list[str] = []
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(windows_module, "STOP_REQUEST_PATH", stop_request)
    monkeypatch.setattr(manager, "_set_autostart", autostart.append)

    manager.install()

    script = definition.read_text(encoding="utf-8")
    # The supervisor is a Python script, not a batch file.
    assert "suzent.service.runtime" in script
    assert "MAX_RETRIES" in script
    assert "code == 73" in script
    # repr() escapes backslashes in the generated script on Windows.
    assert repr(str(stop_request)) in script
    # Must use CREATE_NO_WINDOW for the subprocess, never DETACHED_PROCESS
    # (the two flags are MSDN-incompatible).
    assert "CREATE_NO_WINDOW" in script
    assert "DETACHED_PROCESS" not in script
    # No cmd.exe in the chain — the whole point of the .pyw supervisor.
    assert "cmd.exe" not in script
    compile(script, str(definition), "exec")
    # Autostart points directly to pythonw.exe + the supervisor (no separate launcher).
    assert len(autostart) == 1
    assert "pythonw.exe" in autostart[0]
    assert str(definition) in autostart[0]


def test_windows_start_ensures_autostart_before_process_check(tmp_path, monkeypatch):
    manager = WindowsServiceManager()
    runtime_dir = tmp_path / "Suzent Data"
    runtime_dir.mkdir()
    definition = runtime_dir / "service-supervisor.pyw"
    autostart: list[str] = []
    definition.write_text("# supervisor\n", encoding="utf-8")
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    # Simulate a stale autostart pointing to the old cmd.exe launcher.
    monkeypatch.setattr(
        manager,
        "_read_autostart",
        lambda: f'cmd.exe /d /c "{definition}"',
    )
    monkeypatch.setattr(manager, "_set_autostart", autostart.append)
    monkeypatch.setattr(windows_module, "read_process_state", lambda: object())

    manager.start()

    # Autostart was migrated to the new pythonw.exe + supervisor path.
    assert autostart == [manager._autostart_command()]
    assert "pythonw.exe" in autostart[0]


def test_windows_uninstall_removes_supervisor_and_legacy_files(tmp_path, monkeypatch):
    manager = WindowsServiceManager()
    definition = tmp_path / "service-supervisor.pyw"
    stop_request = tmp_path / "service-stop.request"
    legacy_cmd = tmp_path / "service-supervisor.cmd"
    legacy_launcher = tmp_path / "service-launcher.pyw"
    definition.write_text("# supervisor\n", encoding="utf-8")
    legacy_cmd.write_text("@echo off\n", encoding="utf-8")
    legacy_launcher.write_text("# launcher\n", encoding="utf-8")
    stop_request.touch()
    deleted_autostart: list[bool] = []
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(windows_module, "STOP_REQUEST_PATH", stop_request)
    monkeypatch.setattr(windows_module, "_LEGACY_CMD", legacy_cmd)
    monkeypatch.setattr(windows_module, "_LEGACY_LAUNCHER", legacy_launcher)
    monkeypatch.setattr(
        manager, "_delete_autostart", lambda: deleted_autostart.append(True)
    )
    monkeypatch.setattr(manager, "stop", lambda: None)

    manager.uninstall()

    assert deleted_autostart == [True]
    assert not definition.exists()
    assert not legacy_cmd.exists()
    assert not legacy_launcher.exists()
    assert not stop_request.exists()
