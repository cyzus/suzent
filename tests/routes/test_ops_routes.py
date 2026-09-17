"""Tests for the web console's service-control routes.

The interesting cases are the two where the route can act on the process
running it: a restart must answer before it takes itself down, and a disable
must refuse rather than strand the console.
"""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from suzent.routes import ops_routes
from suzent.service.models import ServiceStatus


@pytest.fixture
def client() -> TestClient:
    app = Starlette(
        routes=[
            Route("/ops/service/status", ops_routes.get_ops_status, methods=["GET"]),
            Route(
                "/ops/service/restart", ops_routes.restart_ops_service, methods=["POST"]
            ),
            Route(
                "/ops/service/enabled",
                ops_routes.set_ops_service_enabled,
                methods=["POST"],
            ),
            Route("/ops/logs", ops_routes.get_ops_logs, methods=["GET"]),
        ]
    )
    return TestClient(app)


class FakeController:
    """A ServiceController stand-in that records what was asked of it."""

    def __init__(self, *, installed: bool = True, running: bool = True):
        self.calls: list[str] = []
        self._installed = installed
        self._running = running
        self.platform_manager = SimpleNamespace(is_installed=lambda: self._installed)

    def status(self) -> ServiceStatus:
        return ServiceStatus(
            installed=self._installed,
            autostart=self._installed,
            running=self._running,
            ready=self._running,
            pid=4321 if self._running else None,
            port=25314 if self._running else None,
            version="1.2.3" if self._running else None,
            uptime_seconds=61.0 if self._running else None,
            rss_bytes=1024 if self._running else None,
        )

    def restart(self) -> None:
        self.calls.append("restart")

    def install(self) -> None:
        self.calls.append("install")
        self._installed = True

    def uninstall(self) -> None:
        self.calls.append("uninstall")
        self._installed = False


@pytest.fixture
def controller(monkeypatch) -> FakeController:
    fake = FakeController()
    monkeypatch.setattr(ops_routes, "get_service_controller", lambda: fake)
    return fake


def _set_self_managed(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(ops_routes, "_serving_process_is_the_service", lambda: value)


# ── status ──────────────────────────────────────────────────────────────


def test_status_reports_the_service_and_who_is_serving(client, controller, monkeypatch):
    _set_self_managed(monkeypatch, True)
    body = client.get("/ops/service/status").json()
    assert body["installed"] is True
    assert body["ready"] is True
    assert body["pid"] == 4321
    # The console needs this to know a restart will cut its own connection.
    assert body["self_managed"] is True
    assert body["log_path"].endswith("server.log")


def test_status_surfaces_a_platform_failure_as_500(client, monkeypatch):
    def explode() -> None:
        raise OSError("launchctl unavailable")

    monkeypatch.setattr(ops_routes, "get_service_controller", explode)
    response = client.get("/ops/service/status")
    assert response.status_code == 500
    assert "launchctl" in response.json()["error"]


# ── self-identification ─────────────────────────────────────────────────


def test_only_a_service_run_mode_process_can_be_the_service(monkeypatch):
    monkeypatch.delenv("SUZENT_RUN_MODE", raising=False)
    # A desktop or `suzent serve` backend is never the service, even if a
    # service happens to be running with this PID recorded.
    monkeypatch.setattr(
        ops_routes, "read_process_state", lambda: SimpleNamespace(pid=os.getpid())
    )
    assert ops_routes._serving_process_is_the_service() is False

    monkeypatch.setenv("SUZENT_RUN_MODE", "service")
    assert ops_routes._serving_process_is_the_service() is True

    # A service running as some *other* process is fair game to stop.
    monkeypatch.setattr(
        ops_routes, "read_process_state", lambda: SimpleNamespace(pid=os.getpid() + 1)
    )
    assert ops_routes._serving_process_is_the_service() is False

    monkeypatch.setattr(ops_routes, "read_process_state", lambda: None)
    assert ops_routes._serving_process_is_the_service() is False


# ── restart ─────────────────────────────────────────────────────────────


def test_restart_of_another_process_happens_inline(client, controller, monkeypatch):
    _set_self_managed(monkeypatch, False)
    response = client.post("/ops/service/restart")
    assert response.status_code == 200
    assert controller.calls == ["restart"]


def test_restart_of_self_is_acknowledged_with_202(client, controller, monkeypatch):
    """A self-restart reports differently, so the console can expect a gap.

    That the restart really is deferred past the response is asserted in
    ``test_deferred_self_restart_eventually_runs``; TestClient keeps draining
    its event loop after the response, so ordering cannot be observed here.
    """
    _set_self_managed(monkeypatch, True)
    monkeypatch.setattr(ops_routes, "_SELF_ACTION_DELAY_SECONDS", 0.01)

    response = client.post("/ops/service/restart")
    assert response.status_code == 202
    assert response.json() == {"status": "restarting", "self_managed": True}


@pytest.mark.asyncio
async def test_deferred_self_restart_eventually_runs(controller, monkeypatch):
    _set_self_managed(monkeypatch, True)
    monkeypatch.setattr(ops_routes, "_SELF_ACTION_DELAY_SECONDS", 0.01)

    request = SimpleNamespace()
    response = await ops_routes.restart_ops_service(request)
    assert response.status_code == 202
    assert controller.calls == []

    await asyncio.sleep(0.1)
    assert controller.calls == ["restart"]


def test_restart_without_an_installed_service_is_a_conflict(
    client, controller, monkeypatch
):
    _set_self_managed(monkeypatch, False)
    controller._installed = False
    response = client.post("/ops/service/restart")
    assert response.status_code == 409
    assert response.json()["error"] == "service_not_installed"
    assert controller.calls == []


# ── enable / disable ────────────────────────────────────────────────────


def test_disabling_the_service_that_serves_the_console_is_refused(
    client, controller, monkeypatch
):
    """The footgun this route exists to close.

    The call would succeed, the console would go dark, and re-enabling it
    needs a shell on the host -- the one thing a remote browser lacks.
    """
    _set_self_managed(monkeypatch, True)
    response = client.post("/ops/service/enabled", json={"enabled": False})
    assert response.status_code == 409
    assert response.json()["error"] == "would_disable_self"
    assert controller.calls == []


def test_disabling_someone_elses_service_is_allowed(client, controller, monkeypatch):
    _set_self_managed(monkeypatch, False)
    response = client.post("/ops/service/enabled", json={"enabled": False})
    assert response.status_code == 200
    assert controller.calls == ["uninstall"]
    assert response.json()["installed"] is False


def test_enabling_is_allowed_even_from_the_service_itself(
    client, controller, monkeypatch
):
    # Installing cannot strand anyone, so the guard must not block it.
    _set_self_managed(monkeypatch, True)
    controller._installed = False
    response = client.post("/ops/service/enabled", json={"enabled": True})
    assert response.status_code == 200
    assert controller.calls == ["install"]


@pytest.mark.parametrize("payload", [{}, {"enabled": "yes"}, {"enabled": 1}, None])
def test_enabled_must_be_a_boolean(client, controller, monkeypatch, payload):
    _set_self_managed(monkeypatch, False)
    response = client.post("/ops/service/enabled", json=payload)
    assert response.status_code == 400
    assert response.json()["error"] == "enabled_must_be_boolean"
    assert controller.calls == []


# ── logs ────────────────────────────────────────────────────────────────


def test_log_tail_returns_the_end_of_the_file(client, tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_text("\n".join(f"line {i}" for i in range(500)), encoding="utf-8")
    monkeypatch.setattr(ops_routes, "LOG_PATH", log)

    body = client.get("/ops/logs?lines=10").json()
    assert body["available"] is True
    assert body["lines"] == [f"line {i}" for i in range(490, 500)]


def test_log_tail_spanning_multiple_read_blocks(client, tmp_path, monkeypatch):
    """The backwards read must stitch blocks in the right order."""
    log = tmp_path / "server.log"
    # Comfortably larger than the 64 KiB block the tail reads in.
    log.write_text("\n".join(f"{i}:{'x' * 200}" for i in range(2000)), encoding="utf-8")
    monkeypatch.setattr(ops_routes, "LOG_PATH", log)

    lines = client.get("/ops/logs?lines=700").json()["lines"]
    assert len(lines) == 700
    assert lines[0].startswith("1300:")
    assert lines[-1].startswith("1999:")


def test_log_tail_is_capped(client, tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_text("\n".join(str(i) for i in range(5000)), encoding="utf-8")
    monkeypatch.setattr(ops_routes, "LOG_PATH", log)

    body = client.get(f"/ops/logs?lines={ops_routes.MAX_LOG_LINES * 10}").json()
    assert len(body["lines"]) == ops_routes.MAX_LOG_LINES


def test_log_tail_survives_undecodable_bytes(client, tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_bytes(b"good line\n\xff\xfe broken\nlast line")
    monkeypatch.setattr(ops_routes, "LOG_PATH", log)

    body = client.get("/ops/logs").json()
    assert body["lines"][0] == "good line"
    assert body["lines"][-1] == "last line"


def test_log_tail_strips_terminal_colour_codes(client, tmp_path, monkeypatch):
    """The file carries the same colour codes the terminal formatter emits."""
    log = tmp_path / "server.log"
    log.write_text(
        "\x1b[32m2026-01-01 INFO\x1b[0m \x1b[1mready\x1b[0m\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ops_routes, "LOG_PATH", log)

    body = client.get("/ops/logs").json()
    assert body["lines"] == ["2026-01-01 INFO ready"]


def test_missing_log_is_reported_not_an_error(client, tmp_path, monkeypatch):
    monkeypatch.setattr(ops_routes, "LOG_PATH", tmp_path / "absent.log")
    body = client.get("/ops/logs").json()
    assert body["available"] is False
    assert body["lines"] == []


def test_a_nonsense_line_count_falls_back_to_the_default(client, tmp_path, monkeypatch):
    log = tmp_path / "server.log"
    log.write_text("\n".join(str(i) for i in range(400)), encoding="utf-8")
    monkeypatch.setattr(ops_routes, "LOG_PATH", log)

    body = client.get("/ops/logs?lines=banana").json()
    assert len(body["lines"]) == ops_routes.DEFAULT_LOG_LINES
