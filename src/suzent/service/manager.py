"""High-level service management and runtime status inspection."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import psutil

from suzent.service.models import ServiceProcessState, ServiceStatus
from suzent.service.platforms import PlatformServiceManager, get_platform_manager
from suzent.service.state import read_process_state
from suzent.version import get_backend_source_root


class ServiceController:
    """Coordinate OS service management with live Suzent process state."""

    def __init__(self, platform_manager: PlatformServiceManager | None = None):
        self.platform_manager = platform_manager or get_platform_manager()

    def install(self, *, start: bool = True) -> None:
        self._assert_service_owned(read_process_state())
        self.platform_manager.install()
        if start:
            self.platform_manager.start()

    def uninstall(self) -> None:
        self._assert_service_owned(read_process_state())
        self.stop()
        self.platform_manager.uninstall()

    def start(self) -> None:
        if not self.platform_manager.is_installed():
            raise RuntimeError("Suzent service is not installed.")
        self._assert_service_owned(read_process_state())
        self.platform_manager.start()

    def stop(self) -> None:
        state = read_process_state()
        self._assert_service_owned(state)
        if state is None:
            self.platform_manager.stop()
            return
        if not self._request_graceful_shutdown(state.port, state.control_token):
            self.platform_manager.stop()
            return
        deadline = time.monotonic() + 15.0
        while read_process_state() is not None and time.monotonic() < deadline:
            time.sleep(0.1)
        if read_process_state() is not None:
            self.platform_manager.stop()

    def restart(self) -> None:
        if not self.platform_manager.is_installed():
            raise RuntimeError("Suzent service is not installed.")
        self.stop()
        self.platform_manager.start()

    @staticmethod
    def _assert_service_owned(state: ServiceProcessState | None) -> None:
        if state is None:
            return
        expected = get_backend_source_root()
        actual = Path(state.source_root).resolve() if state.source_root else None
        if expected is not None and actual == expected.resolve():
            return
        raise RuntimeError(
            f"Running service belongs to {actual or 'an unknown installation'} "
            f"(PID {state.pid}), not {expected or 'this installation'}. "
            "Inspect the other installation and stop it explicitly; no process was stopped."
        )

    @staticmethod
    def _request_graceful_shutdown(port: int, control_token: str) -> bool:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/service/stop",
            method="POST",
            headers={"X-Suzent-Service-Token": control_token},
        )
        try:
            with urllib.request.urlopen(request, timeout=2.0) as response:
                return response.status == 202
        except (OSError, urllib.error.URLError):
            return False

    def status(self) -> ServiceStatus:
        installed = self.platform_manager.is_installed()
        autostart = self.platform_manager.is_autostart_enabled()
        state = read_process_state()
        if state is None:
            return ServiceStatus(
                installed=installed,
                autostart=autostart,
                running=False,
                ready=False,
            )

        try:
            self._assert_service_owned(state)
        except RuntimeError as exc:
            return ServiceStatus(
                installed=installed,
                autostart=autostart,
                running=False,
                ready=False,
                error=str(exc),
            )

        try:
            process = psutil.Process(state.pid)
            rss_bytes = process.memory_info().rss
            started_at = datetime.fromisoformat(state.started_at)
            now = datetime.now(started_at.tzinfo)
            uptime_seconds = max(0.0, now.timestamp() - started_at.timestamp())
        except (ValueError, psutil.Error) as exc:
            return ServiceStatus(
                installed=installed,
                autostart=autostart,
                running=False,
                ready=False,
                error=str(exc),
            )

        ready = self._probe(state.port)
        return ServiceStatus(
            installed=installed,
            autostart=autostart,
            running=True,
            ready=ready,
            pid=state.pid,
            port=state.port,
            version=state.version,
            uptime_seconds=uptime_seconds,
            rss_bytes=rss_bytes,
        )

    @staticmethod
    def _probe(port: int) -> bool:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/ready", timeout=1.0
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            return False
        return payload.get("app") == "suzent" and payload.get("status") == "ready"


def get_service_controller() -> ServiceController:
    return ServiceController()
