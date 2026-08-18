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


def test_windows_service_uses_hkcu_autostart_and_bounded_restarts(
    tmp_path, monkeypatch
):
    manager = WindowsServiceManager()
    runtime_dir = tmp_path / "Suzent Data"
    definition = runtime_dir / "service-supervisor.cmd"
    launcher = runtime_dir / "service-launcher.pyw"
    stop_request = tmp_path / "service-stop.request"
    autostart: list[str] = []
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(
        WindowsServiceManager, "launcher_path", property(lambda _self: launcher)
    )
    monkeypatch.setattr(windows_module, "STOP_REQUEST_PATH", stop_request)
    monkeypatch.setattr(manager, "_set_autostart", autostart.append)

    manager.install()

    script = definition.read_text(encoding="utf-8")
    assert "suzent.service.runtime" in script
    assert "retries" in script
    assert "%code% EQU 73" in script
    assert str(stop_request) in script
    launcher_script = launcher.read_text(encoding="utf-8")
    assert "subprocess.Popen" in launcher_script
    assert "CREATE_NO_WINDOW" in launcher_script
    assert "DETACHED_PROCESS" in launcher_script
    assert "CREATE_NEW_PROCESS_GROUP" in launcher_script
    assert repr(str(definition)) in launcher_script
    compile(launcher_script, str(launcher), "exec")
    assert len(autostart) == 1
    assert "pythonw.exe" in autostart[0]
    assert str(launcher) in autostart[0]
    assert "cmd.exe" not in autostart[0]


def test_windows_start_migrates_visible_autostart_before_process_check(
    tmp_path, monkeypatch
):
    manager = WindowsServiceManager()
    runtime_dir = tmp_path / "Suzent Data"
    runtime_dir.mkdir()
    definition = runtime_dir / "service-supervisor.cmd"
    launcher = runtime_dir / "service-launcher.pyw"
    autostart: list[str] = []
    definition.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(
        WindowsServiceManager, "launcher_path", property(lambda _self: launcher)
    )
    monkeypatch.setattr(
        manager,
        "_read_autostart",
        lambda: f'cmd.exe /d /c "{definition}"',
    )
    monkeypatch.setattr(manager, "_set_autostart", autostart.append)
    monkeypatch.setattr(windows_module, "read_process_state", lambda: object())

    manager.start()

    assert launcher.exists()
    assert autostart == [manager._autostart_command()]
    assert "pythonw.exe" in autostart[0]


def test_windows_uninstall_removes_supervisor_and_hidden_launcher(
    tmp_path, monkeypatch
):
    manager = WindowsServiceManager()
    definition = tmp_path / "service-supervisor.cmd"
    launcher = tmp_path / "service-launcher.pyw"
    stop_request = tmp_path / "service-stop.request"
    definition.write_text("@echo off\n", encoding="utf-8")
    launcher.write_text("# launcher\n", encoding="utf-8")
    stop_request.touch()
    deleted_autostart: list[bool] = []
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(
        WindowsServiceManager, "launcher_path", property(lambda _self: launcher)
    )
    monkeypatch.setattr(windows_module, "STOP_REQUEST_PATH", stop_request)
    monkeypatch.setattr(
        manager, "_delete_autostart", lambda: deleted_autostart.append(True)
    )
    monkeypatch.setattr(manager, "stop", lambda: None)

    manager.uninstall()

    assert deleted_autostart == [True]
    assert not definition.exists()
    assert not launcher.exists()
    assert not stop_request.exists()
