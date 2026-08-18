from __future__ import annotations

from suzent.service import manager as service_manager
from suzent.service.manager import ServiceController
from suzent.service.models import ServiceProcessState
from suzent.service.platforms.base import PlatformServiceManager


class FakePlatformManager(PlatformServiceManager):
    def __init__(self, installed: bool = False):
        self.installed = installed
        self.actions: list[str] = []

    def is_installed(self) -> bool:
        return self.installed

    def install(self) -> None:
        self.actions.append("install")
        self.installed = True

    def uninstall(self) -> None:
        self.actions.append("uninstall")
        self.installed = False

    def start(self) -> None:
        self.actions.append("start")

    def stop(self) -> None:
        self.actions.append("stop")


def _process_state() -> ServiceProcessState:
    return ServiceProcessState(
        instance_id="abc",
        control_token="control-token",
        pid=42,
        process_created_at=1,
        started_at="2026-08-18T00:00:00+00:00",
        port=25314,
        version="0.8.0",
    )


def test_install_can_start_or_only_enable_definition():
    manager = FakePlatformManager()
    controller = ServiceController(manager)

    controller.install(start=False)
    assert manager.actions == ["install"]

    manager.actions.clear()
    controller.install(start=True)
    assert manager.actions == ["install", "start"]


def test_start_requires_an_installed_definition():
    controller = ServiceController(FakePlatformManager())

    try:
        controller.start()
    except RuntimeError as exc:
        assert "not installed" in str(exc)
    else:
        raise AssertionError("start should reject a missing service definition")


def test_status_reports_installed_but_stopped(monkeypatch):
    monkeypatch.setattr(service_manager, "read_process_state", lambda: None)

    status = ServiceController(FakePlatformManager(installed=True)).status()

    assert status.installed is True
    assert status.autostart is True
    assert status.running is False
    assert status.ready is False


def test_status_reports_live_process_resources(monkeypatch):
    state = _process_state()

    class MemoryInfo:
        rss = 123456

    class Process:
        def memory_info(self):
            return MemoryInfo()

    monkeypatch.setattr(service_manager, "read_process_state", lambda: state)
    monkeypatch.setattr(service_manager.psutil, "Process", lambda _pid: Process())
    monkeypatch.setattr(ServiceController, "_probe", staticmethod(lambda _port: True))

    status = ServiceController(FakePlatformManager(installed=True)).status()

    assert status.running is True
    assert status.ready is True
    assert status.pid == 42
    assert status.rss_bytes == 123456
    assert status.version == "0.8.0"


def test_stop_falls_back_when_graceful_endpoint_is_unreachable(monkeypatch):
    platform = FakePlatformManager(installed=True)
    controller = ServiceController(platform)
    monkeypatch.setattr(service_manager, "read_process_state", _process_state)
    monkeypatch.setattr(
        controller, "_request_graceful_shutdown", lambda _port, _token: False
    )

    controller.stop()

    assert platform.actions == ["stop"]


def test_stop_does_not_force_process_after_graceful_exit(monkeypatch):
    platform = FakePlatformManager(installed=True)
    controller = ServiceController(platform)
    states = iter([_process_state(), None, None])
    monkeypatch.setattr(service_manager, "read_process_state", lambda: next(states))
    monkeypatch.setattr(
        controller, "_request_graceful_shutdown", lambda _port, _token: True
    )

    controller.stop()

    assert platform.actions == []
