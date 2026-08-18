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
    definition = tmp_path / "service-supervisor.cmd"
    stop_request = tmp_path / "service-stop.request"
    autostart: list[str] = []
    monkeypatch.setattr(
        WindowsServiceManager, "definition_path", property(lambda _self: definition)
    )
    monkeypatch.setattr(windows_module, "STOP_REQUEST_PATH", stop_request)
    monkeypatch.setattr(manager, "_set_autostart", autostart.append)

    manager.install()

    script = definition.read_text(encoding="utf-8")
    assert "suzent.service.runtime" in script
    assert "retries" in script
    assert "%code% EQU 73" in script
    assert str(stop_request) in script
    assert len(autostart) == 1
    assert "cmd.exe" in autostart[0]
    assert str(definition) in autostart[0]
