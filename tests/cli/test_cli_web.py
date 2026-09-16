"""`suzent web` opens a browser at a backend; it never starts one of its own.

The web UI is a route on the ordinary backend, so this command's whole job is
to pick the right already-serving (or startable) backend. These tests pin that
decision table.
"""

import importlib
from dataclasses import replace

import pytest
from typer.testing import CliRunner

from suzent.service.models import ServiceStatus

cli = importlib.import_module("suzent.cli")
cli_main = importlib.import_module("suzent.cli.main")
runner = CliRunner()

STOPPED = ServiceStatus(installed=False, autostart=False, running=False, ready=False)


class FakeController:
    def __init__(self, status: ServiceStatus, serving: list[bool]):
        self._status = status
        self._serving = serving
        self.calls: list[str] = []

    def status(self) -> ServiceStatus:
        return self._status

    def start(self) -> None:
        self.calls.append("start")
        self._serving[0] = True

    def install(self, *, start: bool = True) -> None:
        self.calls.append(f"install(start={start})")
        self._serving[0] = start


@pytest.fixture
def web_env(monkeypatch):
    """Stub out every side effect `web` can have, and record what it chose."""
    opened: list[str] = []
    spawned: list[list[str]] = []
    monkeypatch.setattr(cli_main.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(
        cli_main.subprocess, "Popen", lambda *a, **kw: spawned.append(a[0])
    )
    monkeypatch.setattr("suzent.webui.webui_available", lambda: True)

    def configure(*, status: ServiceStatus, serving: bool):
        """`serving` is the state *before* the command runs; start/install flip it."""
        flag = [serving]
        controller = FakeController(status, flag)
        monkeypatch.setattr("suzent.service.get_service_controller", lambda: controller)
        monkeypatch.setattr(
            cli_main, "_is_suzent_server_running", lambda host, port, **kw: flag[0]
        )
        return controller

    return configure, opened, spawned


def test_reuses_a_running_service(web_env):
    configure, opened, spawned = web_env
    status = replace(STOPPED, installed=True, running=True, ready=True, port=25314)
    controller = configure(status=status, serving=True)

    result = runner.invoke(cli.app, ["web"])

    assert result.exit_code == 0
    assert opened == ["http://127.0.0.1:25314/"]
    assert controller.calls == []
    assert spawned == []


def test_reuses_a_foreign_backend_without_touching_the_service(web_env):
    """`suzent serve` or the desktop app already owns the port -- just open it."""
    configure, opened, spawned = web_env
    controller = configure(status=STOPPED, serving=True)

    result = runner.invoke(cli.app, ["web"])

    assert result.exit_code == 0
    assert opened == ["http://127.0.0.1:25314/"]
    assert controller.calls == []
    assert spawned == []


def test_starts_an_installed_but_stopped_service(web_env):
    configure, opened, _ = web_env
    status = replace(STOPPED, installed=True, port=25314)
    controller = configure(status=status, serving=False)

    result = runner.invoke(cli.app, ["web"])

    assert result.exit_code == 0
    assert controller.calls == ["start"]
    assert opened == ["http://127.0.0.1:25314/"]


def test_installs_the_service_when_asked(web_env):
    configure, opened, _ = web_env
    controller = configure(status=STOPPED, serving=False)

    result = runner.invoke(cli.app, ["web", "--install"])

    assert result.exit_code == 0
    assert controller.calls == ["install(start=True)"]
    assert opened == ["http://127.0.0.1:25314/"]


def test_declining_the_install_explains_the_alternatives(web_env):
    configure, opened, spawned = web_env
    controller = configure(status=STOPPED, serving=False)

    result = runner.invoke(cli.app, ["web", "--no-install"])

    assert result.exit_code == 1
    assert "suzent service install" in result.output
    assert "--foreground" in result.output
    assert controller.calls == []
    assert spawned == []
    assert opened == []


def test_foreground_spawns_its_own_server(web_env):
    configure, _opened, spawned = web_env
    controller = configure(status=STOPPED, serving=False)

    runner.invoke(cli.app, ["web", "--foreground", "--no-open", "--port", "18099"])

    assert controller.calls == []
    assert spawned and spawned[0][1:] == ["-m", "suzent.server"]


def test_missing_bundle_is_a_clear_error(web_env, monkeypatch):
    configure, _opened, spawned = web_env
    configure(status=STOPPED, serving=True)
    monkeypatch.setattr("suzent.webui.webui_available", lambda: False)

    result = runner.invoke(cli.app, ["web"])

    assert result.exit_code == 1
    assert "build_webui" in result.output
    assert spawned == []
