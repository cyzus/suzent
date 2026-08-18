from __future__ import annotations

import json

from typer.testing import CliRunner

from suzent.cli import service as service_cli
from suzent.service.models import ServiceStatus


class _Controller:
    def __init__(self, status: ServiceStatus):
        self._status = status
        self.actions: list[object] = []

    def status(self) -> ServiceStatus:
        return self._status

    def install(self, *, start: bool = True) -> None:
        self.actions.append(("install", start))

    def uninstall(self) -> None:
        self.actions.append("uninstall")

    def start(self) -> None:
        self.actions.append("start")

    def stop(self) -> None:
        self.actions.append("stop")

    def restart(self) -> None:
        self.actions.append("restart")


def test_status_json_is_machine_readable(monkeypatch) -> None:
    controller = _Controller(
        ServiceStatus(
            installed=True,
            autostart=True,
            running=True,
            ready=True,
            pid=123,
            port=25314,
            version="0.8.0",
            uptime_seconds=60,
            rss_bytes=100,
        )
    )
    monkeypatch.setattr(service_cli, "get_service_controller", lambda: controller)

    result = CliRunner().invoke(service_cli.service_app, ["status", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["pid"] == 123


def test_install_can_enable_without_starting(monkeypatch) -> None:
    controller = _Controller(ServiceStatus(False, False, False, False))
    monkeypatch.setattr(service_cli, "get_service_controller", lambda: controller)

    result = CliRunner().invoke(service_cli.service_app, ["install", "--no-start"])

    assert result.exit_code == 0
    assert controller.actions == [("install", False)]


def test_doctor_fails_for_installed_service_that_is_not_ready(monkeypatch) -> None:
    controller = _Controller(ServiceStatus(True, True, True, False))
    monkeypatch.setattr(service_cli, "get_service_controller", lambda: controller)

    result = CliRunner().invoke(service_cli.service_app, ["doctor"])

    assert result.exit_code == 1
    assert "Runtime readiness" in result.stdout
